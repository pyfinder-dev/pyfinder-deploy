"""Offline finite-caller tests; Docker and operational data are never used."""

import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    import verify_caller_boundary as probe
finally:
    sys.path.pop(0)


IMAGE_ID = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64


class CallerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.runtime = self.root / "runtime"
        self.inputs = self.runtime / "shakemap/data/inputs"
        self.inputs.mkdir(parents=True)
        self.source = self.root / "source"
        for name in probe.MODULES:
            path = self.source / "pyfinder" / (name.replace(".", "/") + ".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# distinct installed-source fixture: " + name)
        runtime_patch = patch.object(probe.deployment, "PYFINDER_RUNTIME", self.runtime)
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)
        self.settings = {
            "SHAKEMAP_RUNTIME_ROOT": str(self.runtime),
            "PYFINDER_REPOSITORY": str(self.source),
            "PYFINDER_SHAKEMAP_ENABLED": "false",
            "PYFINDER_SHAKEMAP_URL": "http://service.test:9010",
            "PYFINDER_SHAKEMAP_INPUT_DIRECTORY": probe.deployment.INPUT_TARGET,
            "PYFINDER_SHAKEMAP_CONFIGURATION": "global",
            "PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS": "30",
            "PYFINDER_SHAKEMAP_OVERWRITE": "true",
        }
        self.evidence = self.root / "evidence"
        self.calls = []
        self.exists = False
        self.owner = probe.OWNER
        self.behavior = "success"
        self.calculation = {"classification": "NATIVE_TERMINAL", "outcome": "SUCCESS"}
        self.image = {
            "Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64",
            "Config": {
                "User": "1000:1000",
                "Entrypoint": ["/usr/local/bin/pyfinder-entrypoint"],
                "Cmd": ["continuous"],
                "Labels": {"org.opencontainers.image.base.name": probe.BASE,
                           "io.pyfinder.python.version": "3.12.13"},
            },
        }

    def command(self, arguments, **options):
        """Simulate only the exact Docker calls this bounded probe may use."""
        self.calls.append((arguments, options))
        result = lambda text="", code=0: SimpleNamespace(stdout=text, stderr="", returncode=code)
        if arguments[1:3] == ["container", "ls"]:
            return result(probe.CONTAINER if self.exists else "")
        if arguments[1:3] == ["image", "inspect"]:
            return result(json.dumps([self.image]))
        if arguments[1:3] == ["container", "inspect"]:
            return result(f"{CONTAINER_ID}|{self.owner}")
        if arguments[1:3] == ["container", "rm"]:
            self.assertEqual(arguments[-1], CONTAINER_ID)
            self.exists = False
            return result()
        self.assertEqual(arguments[1], "run")
        cid = Path(arguments[arguments.index("--cidfile") + 1])
        cid.write_text(CONTAINER_ID)
        # Read context as literal AST data, never execute the container script.
        tree = ast.parse(options["input"])
        context = json.loads(tree.body[1].value.args[0].value)
        self.context = context
        self.assertEqual((self.inputs / context["host_marker"]).read_text(), context["nonce"])
        (self.inputs / context["caller_marker"]).write_text(context["nonce"])
        if self.behavior == "timeout":
            self.exists = True
            raise subprocess.TimeoutExpired(arguments, options["timeout"])
        if self.behavior == "failure":
            return result("finite failure", 9)
        returned = {"module_hashes": context["module_hashes"]}
        if "calculation_fixture" in context:
            returned["calculation"] = self.calculation
        return result("PYFINDER_CALLER_PROBE=" + json.dumps(returned))

    def verify(self):
        with patch.object(probe, "command", side_effect=self.command):
            return probe.verify(self.settings, self.evidence)

    def test_success_pins_image_and_checks_real_shared_marker_without_source_mount(self):
        result = self.verify()
        arguments, options = next(call for call in self.calls if call[0][1] == "run")
        self.assertEqual(arguments[-3:], [IMAGE_ID, "-I", "-"])
        self.assertEqual(arguments[arguments.index("--name") + 1], "pyfinder-docker")
        self.assertEqual(arguments[arguments.index("--user") + 1], "1000:1000")
        self.assertEqual(arguments[arguments.index("--entrypoint") + 1], probe.PYTHON)
        self.assertEqual(arguments.count("--mount"), 1)
        self.assertEqual(arguments[arguments.index("--mount") + 1],
                         f"type=bind,source={self.runtime},target=/home/sysop/runtime")
        self.assertNotIn(str(self.source), arguments)
        self.assertEqual(options["timeout"], 120)
        self.assertEqual(options["env"]["PYFINDER_SHAKEMAP_ENABLED"], "false")
        self.assertEqual(set(result["module_hashes"]), set(probe.MODULES))
        self.assertTrue(result["host_shared_bytes_verified"])
        self.assertEqual(list(self.inputs.iterdir()), [])
        self.assertTrue(json.loads((self.evidence / "summary.json").read_text())["passed"])
        self.assertEqual(self.evidence.stat().st_mode & 0o777, 0o700)

    def test_canonical_collision_never_launches_or_creates_evidence(self):
        self.exists = True
        with self.assertRaisesRegex(probe.deployment.DeploymentError, "exists"):
            self.verify()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.evidence.exists())
        self.assertEqual(list(self.inputs.iterdir()), [])

    def test_invalid_image_identity_or_command_is_rejected(self):
        original = deepcopy(self.image)
        for defect in ("id", "entrypoint", "base"):
            self.image = deepcopy(original)
            if defect == "id":
                self.image["Id"] = "mutable-tag"
            elif defect == "entrypoint":
                self.image["Config"]["Entrypoint"] = ["unsafe"]
            else:
                self.image["Config"]["Labels"]["org.opencontainers.image.base.name"] = "other-base"
            with self.subTest(defect=defect), self.assertRaises(probe.deployment.DeploymentError):
                self.verify()
            self.assertFalse(self.evidence.exists())
            self.assertFalse(any(call[0][1] == "run" for call in self.calls))

    def test_timeout_removes_only_owned_container_and_probe_markers(self):
        self.behavior = "timeout"
        with self.assertRaises(subprocess.TimeoutExpired):
            self.verify()
        removals = [call[0] for call in self.calls if call[0][1:3] == ["container", "rm"]]
        self.assertEqual(removals, [["docker", "container", "rm", "--force", CONTAINER_ID]])
        self.assertEqual(list(self.inputs.iterdir()), [])
        self.assertFalse(json.loads((self.evidence / "summary.json").read_text())["passed"])

    def test_timeout_never_removes_a_container_with_changed_owner(self):
        self.behavior = "timeout"
        self.owner = "another-owner"
        with self.assertRaises(subprocess.TimeoutExpired) as error:
            self.verify()
        self.assertFalse(any(call[0][1:3] == ["container", "rm"] for call in self.calls))
        self.assertTrue(self.exists)
        self.assertIn("ownership differs", " ".join(error.exception.__notes__))
        report = json.loads((self.evidence / "summary.json").read_text())
        self.assertEqual(report["failure"]["type"], "TimeoutExpired")
        self.assertIn("120 second", report["failure"]["phase"])
        self.assertIn("ownership differs", report["cleanup_errors"][0])

    def test_failed_finite_process_is_not_reported_as_success(self):
        self.behavior = "failure"
        with self.assertRaisesRegex(probe.deployment.DeploymentError, "exited 9"):
            self.verify()
        self.assertEqual(list(self.inputs.iterdir()), [])
        self.assertFalse(json.loads((self.evidence / "summary.json").read_text())["passed"])

    def test_existing_marker_is_preserved_even_if_its_contents_match(self):
        nonce = "c" * 32
        marker = self.inputs / (".pyfinder-boundary-" + nonce + "-host")
        marker.write_text(nonce)
        with patch.object(probe, "uuid4", return_value=SimpleNamespace(hex=nonce)):
            with self.assertRaises(FileExistsError):
                self.verify()
        self.assertEqual(marker.read_text(), nonce)
        self.assertFalse(any(call[0][1] == "run" for call in self.calls))

    def test_changed_marker_cleanup_is_refused(self):
        marker = self.inputs / "changed"
        marker.write_text("unrelated data")
        with self.assertRaisesRegex(probe.deployment.DeploymentError, "ownership changed"):
            probe.cleanup_marker(marker, "our nonce")
        self.assertEqual(marker.read_text(), "unrelated data")

    def test_evidence_cannot_reuse_or_write_into_runtime(self):
        for target in (self.runtime / "evidence", self.root):
            self.evidence = target
            with self.subTest(target=target), self.assertRaises(probe.deployment.DeploymentError):
                self.verify()
        self.assertEqual(self.calls, [])

    def prepare_native(self):
        from test_calculation_fixture import FIXTURE, EVENT_ID
        (self.runtime / "pyfinder/playbacks").mkdir(parents=True)
        for name in ("finderutils", "eventcontext"):
            (self.source / "pyfinder" / (name + ".py")).write_text("# fixture source")
        return deepcopy(FIXTURE), EVENT_ID

    def test_explicit_native_mode_reuses_single_mount_and_preserves_expected_failure(self):
        fixture, event_id = self.prepare_native()
        fixture["configuration"] = "france"
        self.calculation["outcome"] = "FAILED"
        with patch.object(probe, "command", side_effect=self.command):
            result = probe.verify(self.settings, self.evidence, fixture=fixture,
                                  event_id=event_id, expected_outcome="FAILED")
        arguments, options = next(call for call in self.calls if call[0][1] == "run")
        self.assertEqual(options["timeout"], 780)
        self.assertEqual(arguments.count("--mount"), 1)
        self.assertEqual(self.context["calculation_fixture"]["configuration"], "france")
        self.assertIn("/pyfinder/playbacks/" + event_id + "/", self.context["calculation_workspace"])
        self.assertEqual(result["calculation"]["outcome"], "FAILED")
        self.assertEqual(len(result["module_hashes"]), len(probe.MODULES) + 2)

    def test_harness_failure_never_passes_expected_native_failure(self):
        fixture, event_id = self.prepare_native()
        self.calculation = {"classification": "HARNESS_FAILED", "outcome": "FAILED"}
        with patch.object(probe, "command", side_effect=self.command):
            with self.assertRaisesRegex(probe.deployment.DeploymentError, "validated terminal evidence"):
                probe.verify(self.settings, self.evidence, fixture=fixture,
                             event_id=event_id, expected_outcome="FAILED")
        report = json.loads((self.evidence / "summary.json").read_text())
        self.assertFalse(report["passed"])
        self.assertEqual(report["result"]["calculation"]["outcome"], "FAILED")

    def test_existing_native_workspace_is_refused_before_docker(self):
        fixture, event_id = self.prepare_native()
        existing = self.runtime / "pyfinder/playbacks" / event_id
        existing.mkdir()
        with patch.object(probe, "command", side_effect=self.command):
            with self.assertRaisesRegex(probe.deployment.DeploymentError, "workspace already exists"):
                probe.verify(self.settings, self.evidence, fixture=fixture, event_id=event_id)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.evidence.exists())

    def test_enabled_settings_are_rejected_without_docker_calls(self):
        self.settings["PYFINDER_SHAKEMAP_ENABLED"] = "true"
        with self.assertRaisesRegex(probe.deployment.DeploymentError, "disabled"):
            self.verify()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
