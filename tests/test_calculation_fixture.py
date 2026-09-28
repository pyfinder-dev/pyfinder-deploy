"""Offline safety and evidence checks for explicitly requested native fixtures."""

import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    import calculation_fixture as fixture_probe
    import verify_caller_boundary as boundary
finally:
    sys.path.pop(0)


EVENT_ID = "pyfinder-verification-global-fresh_t00000"
FIXTURE = {
    "synthetic": True, "configuration": "global",
    "origin_time": "2026-09-26T12:30:15.250000Z",
    "latitude": 42.05, "longitude": 13.0, "depth_km": 6.0, "magnitude": 5.5,
    "stations": [
        {"network": "XX", "station": "S01", "location": "00", "channel": channel,
         "latitude": 42.02, "longitude": 13.02, "pga_cm_s2": 98.0665}
        for channel in ("HNE", "HNN")
    ],
}


class CalculationFixtureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # Host tests read the sibling checkout; the real probe imports only the
        # installed image and separately checks its source hashes and origins.
        project = str(SCRIPTS.parents[1] / "pyfinder")
        sys.path.insert(0, project)
        self.addCleanup(lambda: sys.path.remove(project))
        self.service = self.root / "shakemap"
        self.playbacks = self.root / "pyfinder/playbacks"
        self.playbacks.mkdir(parents=True)
        for branch in ("data/inputs", "products", ".service/events", ".service/archive"):
            (self.service / branch).mkdir(parents=True)
        self.workspace = self.playbacks / EVENT_ID / "shakemap-verification"
        self.context = {
            "calculation_fixture": deepcopy(FIXTURE), "event_id": EVENT_ID,
            "host_service": str(self.service), "calculation_workspace": str(self.workspace),
        }
        self.client = Mock()
        self.client.configuration.return_value = {"shared_service_root": str(self.service)}
        self.client.configurations.return_value = {"configurations": ["global", "france"]}
        self.client.queue.return_value = {"capacity": {"running": 0, "queued": 0}}
        self.client.events.return_value = {"jobs": []}
        self.record = {
            "submission_state": "ACCEPTED", "internal_sequence": 8,
            "request": {"event_id": EVENT_ID, "configuration": "global"},
            "acknowledgement": {"event_id": EVENT_ID, "internal_sequence": 8},
            "observation": {"details": {
                "internal_sequence": 8, "status": "SUCCESS", "products_ready": True, "job_completed": True,
                "shared_paths": {name: None for name in (
                    "service_log", "shake_log", "provenance", "product_manifest")},
            }},
        }
        self.workflow = Mock()
        self.workflow.submit.return_value = self.record
        self.workflow.poll.return_value = self.record
        self.workflow.get.return_value = self.record
        self.files = {"event.xml": b"<earthquake/>", "event_dat.xml": b"<stationlist/>"}

    def run_fixture(self, *, terminal=None, clock=None):
        # Only the installed workflow boundary is replaced here; actual input
        # ownership and exclusive workspace creation exercise real filesystem code.
        with patch.object(fixture_probe, "prepare_fixture", return_value=self.files), \
             patch("pyfinder.services.shakemap_workflow.ShakeMapWorkflow", return_value=self.workflow), \
             patch.object(fixture_probe, "verify_terminal", **(
                 {"side_effect": terminal} if isinstance(terminal, Exception)
                 else {"return_value": terminal or {"outcome": "SUCCESS"}})):
            options = {} if clock is None else {"clock": clock}
            return fixture_probe.run_calculation(
                self.context, self.client, local_service=self.service, sleeper=lambda _: None, **options)

    def test_existing_workspace_is_byte_unchanged_and_never_submitted(self):
        self.workspace.mkdir(parents=True)
        original = b"operator evidence must survive\n"
        summary = self.workspace / "calculation-summary.json"
        summary.write_bytes(original)
        result = self.run_fixture()
        self.assertEqual(result["classification"], "HARNESS_FAILED")
        self.assertEqual(summary.read_bytes(), original)
        self.assertEqual(list(self.workspace.iterdir()), [summary])
        self.workflow.submit.assert_not_called()

    def test_every_service_collision_prevents_workspace_and_post(self):
        for branch in ("data/inputs", "products", ".service/events", ".service/archive"):
            path = self.service / branch / (EVENT_ID + "-20260101" if branch.endswith("archive") else EVENT_ID)
            path.mkdir()
            with self.subTest(branch=branch):
                self.assertEqual(self.run_fixture()["classification"], "HARNESS_FAILED")
                self.assertFalse(self.workspace.exists())
                self.workflow.submit.assert_not_called()
            path.rmdir()
        self.client.events.return_value = {"jobs": [{"event_id": EVENT_ID}]}
        self.assertEqual(self.run_fixture()["classification"], "HARNESS_FAILED")
        self.workflow.submit.assert_not_called()

    def test_submit_once_with_explicit_profile_and_exact_sequence(self):
        self.context["calculation_fixture"]["configuration"] = "france"
        self.record["observation"]["details"]["status"] = "FAILED"
        result = self.run_fixture(terminal={"outcome": "FAILED"})
        self.assertEqual(result["classification"], "NATIVE_TERMINAL")
        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["internal_sequence"], 8)
        self.assertFalse(result["deployment_ready"])
        self.workflow.submit.assert_called_once_with(
            "fixture", EVENT_ID, self.files, configuration="france", overwrite=True)
        self.assertTrue((self.workspace / "accepted.json").is_file())

    def test_native_failure_survives_evidence_validation_failure(self):
        self.record["observation"]["details"]["status"] = "FAILED"
        result = self.run_fixture(terminal=ValueError("missing provenance"))
        self.assertEqual(result["classification"], "HARNESS_FAILED")
        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["internal_sequence"], 8)
        self.assertEqual(json.loads((self.workspace / "calculation-summary.json").read_text()), result)

    def test_null_log_paths_do_not_hide_timeout(self):
        self.record["observation"]["details"]["status"] = "QUEUED"
        result = self.run_fixture(clock=Mock(side_effect=[0, 1, 601]))
        self.assertEqual(result["classification"], "TIMEOUT")
        self.assertTrue((self.workspace / "calculation-summary.json").exists())
        self.workflow.submit.assert_called_once()

    def test_uncertain_post_is_retained_and_never_retried(self):
        self.workflow.submit.side_effect = TimeoutError("lost acknowledgement")
        self.workflow.get.return_value = {"submission_state": "UNCERTAIN"}
        result = self.run_fixture()
        self.assertEqual(result["classification"], "SUBMISSION_UNCERTAIN")
        self.workflow.submit.assert_called_once()
        self.workflow.poll.assert_not_called()
        self.assertTrue((self.workspace / "last-record.json").exists())

    def test_changed_sequence_is_a_harness_failure_without_resubmission(self):
        changed = deepcopy(self.record)
        changed["internal_sequence"] = 9
        self.workflow.poll.return_value = changed
        result = self.run_fixture()
        self.assertEqual(result["classification"], "HARNESS_FAILED")
        self.assertIn("sequence changed", result["error"]["message"])
        self.workflow.submit.assert_called_once()

    def test_schema_rejects_ambiguous_time_units_and_component_duplication(self):
        for key, value in (("origin_time", "2026-09-26T12:30:15"), ("latitude", True),
                           ("configuration", "../global"), ("magnitude", float("nan"))):
            fixture = deepcopy(FIXTURE)
            fixture[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                fixture_probe.validate_fixture(fixture, EVENT_ID)
        fixture = deepcopy(FIXTURE)
        fixture["stations"][1] = deepcopy(fixture["stations"][0])
        with self.assertRaises(ValueError):
            fixture_probe.validate_fixture(fixture, EVENT_ID)

    def test_installed_manager_preparation_preserves_physical_origin_and_pga_units(self):
        with patch.dict(os.environ, {"PARAMWS_LOG_FILE": str(self.root / "paramws.log")}):
            files = fixture_probe.prepare_fixture(FIXTURE, EVENT_ID)
        event = ElementTree.fromstring(files["event.xml"])
        self.assertEqual(event.attrib["id"], EVENT_ID)
        self.assertAlmostEqual(float(event.attrib["lat"]), 42.05)
        self.assertAlmostEqual(float(event.attrib["mag"]), 5.5)
        # 98.0665 cm/s² is exactly ten percent of standard gravity.
        stations = ElementTree.fromstring(files["event_dat.xml"])
        values = [float(pga.attrib["value"]) for pga in stations.findall(".//{*}acc")]
        self.assertEqual(len(values), 2)
        for value in values:
            self.assertAlmostEqual(value, 10.0)
        self.assertIn("2026-09-26T12:30:15.250000", files["event.xml"].decode())

    def test_mapping_rejects_missing_redirected_or_outside_evidence(self):
        for value in (None, "/unrelated/log", str(self.service / "../log")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fixture_probe.mapped_service_path(value, self.service, self.service)
        outside = self.root / "outside"
        outside.write_text("unrelated")
        redirected = self.service / "redirected"
        redirected.symlink_to(outside)
        with self.assertRaises(ValueError):
            fixture_probe.mapped_service_path(str(redirected), self.service, self.service)

    def terminal_evidence(self, configuration="global", status="SUCCESS"):
        """Build a small exact manifest; these are evidence tests, not science."""
        self.workspace.mkdir(parents=True)
        self.context["calculation_fixture"]["configuration"] = configuration
        self.record["request"]["configuration"] = configuration
        details = self.record["observation"]["details"]
        details.update(status=status, products_ready=status == "SUCCESS")
        event_service = self.service / ".service/events" / EVENT_ID
        snapshot = event_service / "request"
        snapshot.mkdir(parents=True)
        for name, contents in self.files.items():
            (snapshot / name).write_bytes(contents)
        profile = event_service / "profile/install/config"
        profile.mkdir(parents=True)
        identities = []
        datasets = {"global": {}}
        for setting, name, relative in (
            ("vs30file", "vs30", "global/vs30/global_vs30.grd"),
            ("topography", "topography", "global/topo/topo_30sec.grd"),
        ):
            asset = self.service / "data" / relative
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"synthetic evidence bytes " + name.encode())
            datasets["global"][name] = {"manifest_identity": fixture_probe.file_identity(asset)}
        for name in fixture_probe.REGIONAL_FILES:
            content = "# synthetic profile evidence\n"
            if name == "model.conf":
                content += "vs30file = " + str(self.service / "data/global/vs30/global_vs30.grd") + "\n"
            if name == "products.conf":
                content += "topography = " + str(self.service / "data/global/topo/topo_30sec.grd") + "\n"
            (profile / name).write_text(content)
            identities.append({"path": "install/config/" + name,
                               "identity": fixture_probe.file_identity(profile / name)})
        source = self.service / "data/regional" / configuration
        if configuration != "global":
            source.mkdir(parents=True)
            for name in fixture_probe.REGIONAL_FILES:
                (source / name).write_bytes((profile / name).read_bytes())
        provenance = {
            "event_id": EVENT_ID, "internal_sequence": 8,
            "request": {"configuration": configuration}, "large_datasets": datasets,
            "configuration": {
                "selected": configuration, "profile_files": identities,
                "materialization": {"materialized": True, "selected_configuration": configuration,
                                    "source_directory": str(source) if configuration != "global" else None},
            },
        }
        products = self.service / "products" / EVENT_ID / "current/products"
        products.mkdir(parents=True)
        inventory = []
        for name in ("shake_result.hdf", "grid.xml", "intensity.jpg"):
            path = products / name
            path.write_bytes(b"synthetic product evidence " + name.encode())
            inventory.append({"path": name, **fixture_probe.file_identity(path)})
        manifest = {
            "event_id": EVENT_ID, "internal_sequence": 8, "partial": False,
            "inventory_failures": [], "products": inventory,
            "required_products": {"passed": True, "checks": [{"passed": True}],
                                  "paths": [item["path"] for item in inventory]},
        }
        details["shared_paths"]["products"] = str(products)
        for name, value in (("provenance", provenance), ("product_manifest", manifest)):
            path = event_service / (name + ".json")
            fixture_probe.save_json(path, value)
            details["shared_paths"][name] = str(path)
        for name in ("service_log", "shake_log"):
            path = event_service / (name + ".log")
            path.write_text("synthetic retained log\n")
            details["shared_paths"][name] = str(path)
        self.client.current_products.return_value = {"event_id": EVENT_ID, "internal_sequence": 8}
        return profile, products

    def validate_terminal(self):
        return fixture_probe.verify_terminal(
            self.record, self.files, self.context["calculation_fixture"], self.workspace,
            self.service, self.service, self.client)

    def test_success_requires_all_manifest_bytes_and_managed_grid_identities(self):
        _, products = self.terminal_evidence()
        self.assertEqual(self.validate_terminal()["outcome"], "SUCCESS")
        (products / "grid.xml").write_bytes(b"corrupted product")
        with self.assertRaisesRegex(ValueError, "Product bytes"):
            self.validate_terminal()

    def test_selected_global_dataset_identity_is_not_assumed_from_presence(self):
        self.terminal_evidence()
        (self.service / "data/global/vs30/global_vs30.grd").write_bytes(b"changed grid")
        with self.assertRaisesRegex(ValueError, "grid differs"):
            self.validate_terminal()

    def test_failed_regional_profile_is_exact_and_retains_logs_without_fallback(self):
        self.terminal_evidence("france", "FAILED")
        self.assertEqual(self.validate_terminal()["outcome"], "FAILED")
        self.assertTrue((self.workspace / "shake_log.log").read_bytes())
        (self.service / "data/regional/france/model.conf").write_text("changed source")
        with self.assertRaisesRegex(ValueError, "differs from selected source"):
            self.validate_terminal()

    def test_global_fallback_is_rejected_even_for_expected_native_failure(self):
        self.terminal_evidence("france", "FAILED")
        provenance_path = Path(self.record["observation"]["details"]["shared_paths"]["provenance"])
        provenance = json.loads(provenance_path.read_text())
        provenance["configuration"]["selected"] = "global"
        fixture_probe.save_json(provenance_path, provenance)
        with self.assertRaisesRegex(ValueError, "caller-selected"):
            self.validate_terminal()

    def test_actual_projected_job_shape_has_identity_only_in_durable_request(self):
        self.terminal_evidence()
        # This minimized fixture is extracted from retained native sequence 8.
        # It preserves the API job projection, which deliberately omits event_id.
        projected = json.loads((SCRIPTS.parent / "tests/fixtures/observed-job-projection.json").read_text())
        self.assertNotIn("event_id", projected["observation"]["details"])
        self.assertNotIn("event_id", self.record["observation"]["details"])
        projected["request"]["event_id"] = EVENT_ID
        projected["acknowledgement"]["event_id"] = EVENT_ID
        projected["observation"]["details"]["shared_paths"] = self.record["observation"]["details"]["shared_paths"]
        self.record = projected
        self.assertEqual(self.validate_terminal()["outcome"], "SUCCESS")

    def test_wrong_request_sequence_or_configuration_is_rejected(self):
        self.terminal_evidence()
        original = deepcopy(self.record)
        for defect in ("request_id", "observed_sequence", "acknowledgement_sequence", "configuration"):
            self.record = deepcopy(original)
            if defect == "request_id":
                self.record["request"]["event_id"] = "another-id"
            elif defect == "observed_sequence":
                self.record["observation"]["details"]["internal_sequence"] = 9
            elif defect == "acknowledgement_sequence":
                self.record["acknowledgement"]["internal_sequence"] = 9
            else:
                self.record["request"]["configuration"] = "france"
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.validate_terminal()

    def test_wrong_provenance_or_manifest_identity_is_rejected(self):
        self.terminal_evidence()
        for name in ("provenance", "product_manifest"):
            path = Path(self.record["observation"]["details"]["shared_paths"][name])
            original = path.read_bytes()
            document = json.loads(original)
            document["event_id"] = "another-id"
            fixture_probe.save_json(path, document)
            with self.subTest(document=name), self.assertRaisesRegex(ValueError, "another calculation"):
                self.validate_terminal()
            path.write_bytes(original)

    def test_container_sqlite_guard_allows_only_owned_workspace_database(self):
        # Compile the actual stdin guard, without executing imports or Docker.
        tree = ast.parse(boundary.CONTAINER_PROBE)
        guard = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "guarded_connect")
        real = Mock()
        namespace = {"Path": Path, "context": {}, "real_connect": real}
        exec(compile(ast.Module(body=[guard], type_ignores=[]), "<guard>", "exec"), namespace)
        connect = namespace["guarded_connect"]
        with self.assertRaises(AssertionError):
            connect(self.workspace / "workflow.sqlite")
        namespace["context"]["calculation_workspace"] = str(self.workspace)
        for path in (":memory:", self.root / "operational.sqlite"):
            with self.assertRaises(AssertionError):
                connect(path)
        with self.assertRaises(AssertionError):
            connect(self.workspace / "workflow.sqlite", uri=True)
        connect(self.workspace / "workflow.sqlite")
        real.assert_called_once()


if __name__ == "__main__":
    unittest.main()
