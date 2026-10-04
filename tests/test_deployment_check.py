"""Confined deployment diagnostics: no Docker, network or operator-state access."""

import importlib.util
import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


deployment = load("deployment_for_check_tests", SCRIPTS / "deployment.py")
checks = load("check_deployment_under_test", SCRIPTS / "check_deployment.py")


class CallerInterfaceTests(unittest.TestCase):
    def test_malformed_json_report_is_rejected_without_stderr_disclosure(self):
        for stdout in ("null", "[]", "{}"):
            result = __import__("subprocess").CompletedProcess([], 0, stdout, "private-password")
            with self.subTest(stdout=stdout), patch.object(checks.subprocess, "run", return_value=result), patch.object(deployment, "environment", return_value={}):
                with self.assertRaisesRegex(ValueError, "unsupported report"):
                    checks.caller_settings(deployment, {"PYFINDER_REPOSITORY": str(SCRIPTS.parent)})


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.runtime = self.root / "runtime"
        self.caller = self.root / "pyfinder"
        self.service = self.root / "shakemap"
        for path in (self.runtime, self.caller, self.service):
            path.mkdir()
        self.config = self.root / "deployment.env"
        self.settings = {
            "PYFINDER_REPOSITORY": str(self.caller), "SHAKEMAP_REPOSITORY": str(self.service),
            "SHAKEMAP_RUNTIME_ROOT": str(self.runtime), "SHAKEMAP_PORT": "9010",
            "SHAKEMAP_MAX_CONCURRENT": "10", "PYFINDER_SHAKEMAP_ENABLED": "true",
            "PYFINDER_SHAKEMAP_URL": "http://service.invalid:9010",
            "PYFINDER_SHAKEMAP_INPUT_DIRECTORY": deployment.INPUT_TARGET,
            "PYFINDER_SHAKEMAP_CONFIGURATION": "global",
            "PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS": "30",
            "PYFINDER_SHAKEMAP_OVERWRITE": "true", "PYFINDER_ALERT_CONFIG": "",
        }
        self.write_settings()
        self.start(patch.object(deployment, "ROOT", self.root))
        self.start(patch.object(deployment, "PYFINDER_RUNTIME", self.runtime))
        self.inventory = self.start(patch.object(deployment, "run", return_value="pyfinder-docker\nshakemap-docker\n"))
        self.inspection = self.start(patch.object(deployment, "inspect", side_effect=self.inspect))
        self.http = self.start(patch.object(deployment, "get_json", side_effect=self.get_json))
        self.caller_check = self.start(patch.object(checks, "caller_settings", return_value={
            "status": "ready", "checks": [], "settings": {}, "fallback": {},
        }))
        self.profile_status = {}
        self.typed_diagnostics = True

    def start(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def write_settings(self):
        self.config.write_text("".join(f"{key}={value}\n" for key, value in self.settings.items()))

    def inspect(self, resource, name):
        if resource == "image":
            return {"Id": name}
        component = "pyfinder" if name == "pyfinder-docker" else "shakemap"
        mounts = [{"Type": "bind", "Source": str(self.runtime), "Destination": "/home/sysop/runtime", "RW": True}]
        if component == "shakemap":
            mounts += [{"Type": "bind", "Source": str(self.runtime / "shakemap/data" / item),
                        "Destination": f"/home/sysop/runtime/shakemap/data/{item}", "RW": False}
                       for item in ("global", "regional", "test")]
        return {"Image": "pyfinder:dev" if component == "pyfinder" else "shakemap-docker:latest",
                "State": {"Running": True}, "Mounts": mounts,
                "Config": {"Env": [f"{key}={value}" for key, value in self.settings.items()
                                   if key in deployment.APPLICATION_KEYS or key == "PYFINDER_ALERT_CONFIG"]}}

    def get_json(self, url):
        if url.endswith("/healthz"):
            return {"ready": True}
        name = url.split("/")[-2]
        return {"configuration": name, "scope": "static", "native_execution": "not_run",
                "status": self.profile_status.get(name, "NO_KNOWN_BLOCKERS"),
                "capabilities": {"native_configuration_diagnostics": self.typed_diagnostics},
                "findings": [{"status": "OK", "config_file": f"/runtime/{name}/model.conf",
                              "key": "vs30file", "resolved_path": f"/data/{name}/vs30.grd",
                              "reason": "Static check", "corrective_action": "Review configured file"}]}

    def report(self):
        return checks.build_report(deployment, self.config)

    def test_selected_global_is_not_blocked_by_unused_regions(self):
        self.profile_status.update(italy="BLOCKED", switzerland="INCOMPLETE")
        report = self.report()
        self.assertEqual(report["status"], "usable")
        self.assertEqual(report["configurations"]["italy"]["status"], "blocked")
        self.assertEqual(report["configurations"]["switzerland"]["status"], "unverified")
        self.assertEqual(report["configurations"]["global"]["findings"][0]["resolved_path"], "/data/global/vs30.grd")

    def test_incomplete_setup_accumulates_missing_settings_and_containers(self):
        self.config.write_text("SHAKEMAP_PORT=9010\n")
        self.inventory.return_value = ""
        report = self.report()
        self.assertEqual(report["status"], "blocked")
        missing = {item.get("key") for item in report["findings"] if item["check"] == "setting"}
        self.assertTrue({"PYFINDER_REPOSITORY", "SHAKEMAP_RUNTIME_ROOT"}.issubset(missing))
        self.assertEqual(len([item for item in report["findings"] if item["check"] == "container"]), 2)
        self.assertEqual(set(report["configurations"]), {"global", "italy", "switzerland"})
        self.caller_check.assert_not_called()

    def test_old_service_endpoint_is_unverified_without_host_fallback(self):
        def old(url):
            if url.endswith("/healthz"):
                return {"ready": True}
            raise deployment.DeploymentError("HTTP unavailable")
        self.http.side_effect = old
        report = self.report()
        self.assertEqual(report["status"], "unverified")
        self.assertTrue(all(item["status"] == "unverified" for item in report["configurations"].values()))

    def test_regional_recovery_remains_conditional_and_installed_caller_unknown(self):
        self.settings["PYFINDER_SHAKEMAP_CONFIGURATION"] = "italy"
        self.write_settings()
        self.profile_status["italy"] = "BLOCKED"
        report = self.report()
        self.assertEqual(report["status"], "unverified")
        self.assertTrue(report["recovery"]["requested_configuration_first"])
        self.assertTrue(report["recovery"]["requires_confirmed_eligible_failure"])
        self.assertEqual(report["recovery"]["installed_caller_behavior"], "unverified")
        self.assertIn("conditional", report["recovery"]["status"])

    def test_blocked_global_cannot_support_regional_recovery(self):
        self.settings["PYFINDER_SHAKEMAP_CONFIGURATION"] = "italy"
        self.write_settings()
        self.profile_status.update({"italy": "BLOCKED", "global": "BLOCKED"})
        self.assertEqual(self.report()["status"], "blocked")

    def test_bad_settings_and_component_errors_do_not_echo_secrets(self):
        self.settings["PYFINDER_SHAKEMAP_URL"] = "http://secret-user:secret-password@example.invalid"
        self.write_settings()
        report = json.dumps(self.report())
        self.assertNotIn("secret-user", report)
        self.assertNotIn("secret-password", report)
        self.assertIn("PYFINDER_SHAKEMAP_URL", report)
        self.caller_check.assert_not_called()

    def test_queue_is_read_only_and_requires_explicit_backlog_decision(self):
        self.inventory.return_value = "shakemap-docker\n"
        path = self.runtime / "pyfinder/state/scheduled_queries.sqlite3"
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE event_tracker(status TEXT, next_query_time TEXT)")
            connection.execute("INSERT INTO event_tracker VALUES ('pending','2000-01-01T00:00:00Z')")
        original = path.read_bytes()
        report = self.report()
        item = next(item for item in report["findings"] if item["check"] == "queue")
        self.assertEqual(item["overdue_pending"], 1)
        self.assertEqual(item["status"], "blocked")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_report_only_invokes_read_only_boundaries(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.report()
        self.assertEqual(before, sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")))
        command = self.inventory.call_args.args[0]
        self.assertEqual(command[:4], ["docker", "container", "ls", "--all"])
        self.assertTrue(all(call.args[0] in {"container", "image"} for call in self.inspection.call_args_list))
        self.assertTrue(all(call.args[0].endswith(("/healthz", "/check")) for call in self.http.call_args_list))

    def test_malformed_health_is_unknown_not_blocked(self):
        original = self.get_json
        for health in ({}, {"ready": "true"}, None, []):
            with self.subTest(health=health):
                self.http.side_effect = lambda url: health if url.endswith("/healthz") else original(url)
                item = next(item for item in self.report()["findings"] if item["check"] == "service_health")
                self.assertEqual(item["status"], "unverified")

    def test_malformed_profile_capabilities_are_unknown(self):
        for capabilities in (None, []):
            response = self.get_json("http://service/configurations/global/check")
            response["capabilities"] = capabilities
            with self.subTest(capabilities=capabilities), patch.object(deployment, "get_json", return_value=response):
                with self.assertRaises(ValueError):
                    checks.profile_report(deployment, "http://service", "global")

    def test_dangling_queue_symlink_is_not_an_empty_installation(self):
        path = self.runtime / "queue.sqlite3"
        path.symlink_to(self.runtime / "missing.sqlite3")
        self.assertEqual(checks.backlog(path, caller_running=False)["status"], "blocked")

    def test_active_or_sidecar_queue_is_never_opened(self):
        path = self.runtime / "queue.sqlite3"
        path.write_bytes(b"closed database placeholder")
        with patch.object(checks.sqlite3, "connect") as connect:
            for running in (True, None):
                self.assertEqual(checks.backlog(path, caller_running=running)["status"], "unverified")
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(path) + suffix)
                sidecar.touch()
                self.assertEqual(checks.backlog(path, caller_running=False)["status"], "unverified")
                sidecar.unlink()
            connect.assert_not_called()

    def test_default_text_has_actions_and_no_routine_image_hashes(self):
        self.inventory.return_value = "shakemap-docker\n"
        text = checks.format_report(self.report())
        self.assertIn("Deployment check: BLOCKED", text)
        self.assertIn("Action: Review prerequisites", text)
        self.assertIn("global: USABLE", text)
        self.assertIn("global is selected", text)
        self.assertNotIn("image_id", text)
        self.assertNotIn("eligible_failure_codes", text)

    def test_profile_text_retains_actionable_locations_and_conditional_recovery(self):
        self.settings["PYFINDER_SHAKEMAP_CONFIGURATION"] = "italy"
        self.write_settings()
        report = self.report()
        report["configurations"]["italy"]["findings"] = [{
            "status": "BROKEN", "reason": "Missing module", "config_file": "/profiles/italy/model.conf",
            "section": ["modeling", "gmpe"], "key": "module", "reference": "regional.Model",
            "resolved_path": "/modules/regional.py", "corrective_action": "Install the configured module",
        }]
        text = checks.format_report(report)
        for value in ("/profiles/italy/model.conf", "modeling / gmpe", "regional.Model",
                      "/modules/regional.py", "Install the configured module", "requested region first",
                      "global native success is not assured"):
            self.assertIn(value, text)

    def test_repeated_endpoint_findings_are_grouped(self):
        self.http.side_effect = deployment.DeploymentError("unavailable")
        text = checks.format_report(self.report())
        self.assertEqual(text.count("configuration-check endpoint is unavailable"), 1)
        self.assertIn("global, italy, switzerland", text)

    def test_json_option_preserves_full_structured_report_and_exit_status(self):
        report = self.report()
        with patch.object(checks, "build_report", return_value=report):
            with redirect_stdout(io.StringIO()) as output:
                code = checks.check(deployment, self.config, json_output=True)
        self.assertEqual(json.loads(output.getvalue()), report)
        self.assertEqual(code, 0)

    def test_json_cli_flag_is_forwarded_only_for_check(self):
        with patch.object(sys, "argv", ["deployment.py", "check", "--json"]), patch.object(deployment, "dispatch", return_value=0) as dispatch:
            self.assertEqual(deployment.main(), 0)
            self.assertTrue(dispatch.call_args.args[0].json)
        with patch.object(sys, "argv", ["deployment.py", "start", "--json"]), patch.object(deployment, "dispatch") as dispatch, redirect_stdout(io.StringIO()), patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                deployment.main()
            self.assertEqual(error.exception.code, 2)
            dispatch.assert_not_called()

    def test_exit_codes_are_explicit(self):
        for status, code in (("usable", 0), ("degraded", 0), ("blocked", 1), ("unverified", 2)):
            with self.subTest(status=status), patch.object(checks, "build_report", return_value={"status": status}), patch("builtins.print"):
                self.assertEqual(checks.check(deployment, self.config), code)


if __name__ == "__main__":
    unittest.main()
