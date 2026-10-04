"""Host-only checks: temporary files and fake components, never operator state."""

import argparse
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "deployment", Path(__file__).resolve().parents[1] / "scripts/deployment.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.pyfinder = self.root / "source pyfinder"
        self.shakemap = self.root / "source shakemap"
        self.runtime = self.root / "runtime"
        runtime_patch = patch.object(deployment, "PYFINDER_RUNTIME", self.runtime)
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)
        for path in (self.pyfinder, self.shakemap, self.runtime):
            path.mkdir()
        for path in (self.pyfinder, self.shakemap):
            (path / "scripts").mkdir()
        self.config = self.root / "deployment.env"
        self.settings = {
            "PYFINDER_REPOSITORY": str(self.pyfinder),
            "SHAKEMAP_REPOSITORY": str(self.shakemap),
            "SHAKEMAP_RUNTIME_ROOT": str(self.runtime),
            "SHAKEMAP_PORT": "9010",
            "SHAKEMAP_MAX_CONCURRENT": "10",
            "PYFINDER_SHAKEMAP_ENABLED": "false",
            "PYFINDER_SHAKEMAP_URL": "",
            "PYFINDER_SHAKEMAP_INPUT_DIRECTORY": deployment.INPUT_TARGET,
            "PYFINDER_SHAKEMAP_CONFIGURATION": "global",
            "PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS": "30",
            "PYFINDER_SHAKEMAP_OVERWRITE": "true",
        }
        self.write_config()

    def write_config(self):
        self.config.write_text("".join(f"{key}={value}\n" for key, value in self.settings.items()))

    def arguments(self, action, component=None, **options):
        return argparse.Namespace(action=action, component=component, config=self.config,
                                  live=options.get("live", False), data_action=options.get("data_action"))

    def configure_service(self):
        self.settings["SHAKEMAP_RUNTIME_ROOT"] = str(self.runtime)
        (self.runtime / "shakemap/data/inputs").mkdir(parents=True, exist_ok=True)
        self.write_config()

    def test_literal_repository_paths_and_consolidated_runtime_are_supported(self):
        self.assertEqual(deployment.load_settings(self.config), self.settings)

    def test_shell_injection_is_refused_without_execution(self):
        marker = self.root / "injected"
        for value in (f"$(touch {marker})", f"`touch {marker}`", "global;touch BAD", "global | cat"):
            with self.subTest(value=value):
                self.settings["PYFINDER_SHAKEMAP_CONFIGURATION"] = value
                self.write_config()
                with self.assertRaises(deployment.DeploymentError):
                    deployment.load_settings(self.config)
                self.assertFalse(marker.exists())

    def test_unknown_duplicate_and_missing_keys_are_rejected(self):
        original = self.config.read_text()
        for text in (original + "UNKNOWN=x\n", original + "SHAKEMAP_PORT=9000\n",
                     original.replace("SHAKEMAP_PORT=9010\n", "")):
            self.config.write_text(text)
            with self.assertRaises(deployment.DeploymentError):
                deployment.load_settings(self.config)

    def test_credentials_are_rejected_without_echoing_them(self):
        self.settings["PYFINDER_SHAKEMAP_URL"] = "http://private-user:private-secret@example.test"
        self.write_config()
        with self.assertRaises(deployment.DeploymentError) as caught:
            deployment.load_settings(self.config)
        self.assertNotIn("private-user", str(caught.exception))
        self.assertNotIn("private-secret", str(caught.exception))

    def test_client_rejected_urls_fail_before_any_helper(self):
        for url in ("http://@host", "http://host:0", "http://host\\path", "http://host/\x7f"):
            self.settings["PYFINDER_SHAKEMAP_URL"] = url
            self.write_config()
            with self.subTest(url=url), patch.object(deployment, "run") as run:
                with self.assertRaises(deployment.DeploymentError):
                    deployment.dispatch(self.arguments("build", "shakemap"))
                run.assert_not_called()

    def test_setup_honors_alternate_configuration_destination(self):
        example = self.root / "deployment.env.example"
        example.write_text("example contents")
        alternate = self.root / "alternate.env"
        runtime = self.root / "runtime"
        with patch.object(deployment, "ROOT", self.root), patch.object(deployment, "PYFINDER_RUNTIME", runtime):
            deployment.setup(alternate)
        self.assertEqual(alternate.read_text(), "example contents")
        self.assertEqual(alternate.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.read_text().splitlines()[0],
                         "PYFINDER_REPOSITORY=" + str(self.pyfinder))

    def test_portable_template_requires_paths_and_preserves_completed_setup(self):
        # Exercise the shipped template in a new temporary deployment, not the
        # operator checkout. Setup must work before its required paths are set.
        template = (deployment.ROOT / "deployment.env.example").read_text()
        (self.root / "deployment.env.example").write_text(template)
        destination = self.root / "first-setup.env"
        with patch.object(deployment, "ROOT", self.root):
            deployment.setup(destination)
            self.assertEqual(destination.read_text(), template)
            with self.assertRaisesRegex(deployment.DeploymentError, "PYFINDER_REPOSITORY"):
                deployment.load_settings(destination)

            completed = template
            for key in ("PYFINDER_REPOSITORY", "SHAKEMAP_REPOSITORY", "SHAKEMAP_RUNTIME_ROOT"):
                completed = completed.replace(key + "=\n", key + "=" + self.settings[key] + "\n")
            completed = completed.replace("PYFINDER_SHAKEMAP_URL=\n", "PYFINDER_SHAKEMAP_URL=http://service.example:9010\n")
            destination.write_text(completed)
            loaded = deployment.load_settings(destination)
            self.assertEqual(loaded["SHAKEMAP_RUNTIME_ROOT"], str(self.runtime))
            self.assertEqual(loaded["PYFINDER_SHAKEMAP_ENABLED"], "false")
            self.assertEqual(loaded["PYFINDER_ALERT_CONFIG"], "")

            deployment.setup(destination)
            self.assertEqual(destination.read_text(), completed)
            self.assertEqual(deployment.load_settings(destination), loaded)

    def test_invalid_scalars_are_rejected(self):
        for key, value in (("SHAKEMAP_PORT", "65536"), ("SHAKEMAP_MAX_CONCURRENT", "0"),
                           ("PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS", "nan"),
                           ("PYFINDER_SHAKEMAP_ENABLED", "yes"),
                           ("PYFINDER_SHAKEMAP_INPUT_DIRECTORY", "/wrong")):
            original = self.settings[key]
            self.settings[key] = value
            self.write_config()
            with self.subTest(key=key), self.assertRaises(deployment.DeploymentError):
                deployment.load_settings(self.config)
            self.settings[key] = original

    def test_unconfigured_operations_have_no_command_side_effects(self):
        self.settings["SHAKEMAP_RUNTIME_ROOT"] = ""
        self.write_config()
        for action, component in (("start", "pyfinder"), ("start", "shakemap"),
                                  ("finalize", "shakemap"), ("verify", None)):
            with self.subTest(action=action, component=component), patch.object(deployment, "run") as run:
                with self.assertRaises(deployment.DeploymentError):
                    deployment.dispatch(self.arguments(action, component))
                run.assert_not_called()

    def test_mutating_component_selection_is_explicit(self):
        with patch.object(deployment, "run") as run:
            for action in ("build", "data", "finalize", "start", "stop"):
                with self.assertRaises(deployment.DeploymentError):
                    deployment.dispatch(self.arguments(action))
            run.assert_not_called()

    def test_component_helper_gets_owner_cwd_and_exact_flags(self):
        self.configure_service()
        recorder = self.root / "record"
        script = self.shakemap / "scripts/start-shakemap-docker.sh"
        script.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@" > "$RECORD_FILE"\n')
        script.chmod(0o755)
        with patch.dict(os.environ, {"RECORD_FILE": str(recorder)}):
            deployment.dispatch(self.arguments("start", "shakemap"))
        self.assertEqual(recorder.read_text().splitlines(),
                         [str(self.shakemap), "--runtime-root", str(self.runtime),
                          "--port", "9010", "--max-concurrent", "10"])

    def test_component_failure_propagates(self):
        script = self.shakemap / "scripts/build-shakemap-docker.sh"
        script.write_text("#!/bin/sh\nexit 17\n")
        script.chmod(0o755)
        with self.assertRaisesRegex(deployment.DeploymentError, "17"):
            deployment.dispatch(self.arguments("build", "shakemap"))

    def test_setup_preserves_local_configuration_and_runtime_contents(self):
        local = self.root / "deployment.env"
        existing = local.read_text()
        runtime = self.root / "runtime"
        state = runtime / "pyfinder/state"
        state.mkdir(parents=True)
        marker = state / "existing.sqlite"
        marker.write_bytes(b"existing operator bytes")

        # Setup owns only missing caller directories. Consolidated service data
        # and historical payloads must remain exactly as the operator left them.
        sibling_markers = []
        for name in ("shakemap/data/inputs", "install-dtgeo"):
            directory = runtime / name
            directory.mkdir(parents=True)
            sibling = directory / "retained"
            sibling.write_bytes(b"retained sibling bytes")
            sibling_markers.append(sibling)

        with patch.object(deployment, "ROOT", self.root), patch.object(deployment, "PYFINDER_RUNTIME", runtime):
            deployment.setup()
            deployment.setup()
        self.assertEqual(local.read_text(), existing)
        self.assertEqual(marker.read_bytes(), b"existing operator bytes")
        for sibling in sibling_markers:
            self.assertEqual(sibling.read_bytes(), b"retained sibling bytes")
        self.assertTrue((runtime / "pyfinder/runs").is_dir())

    def test_setup_refuses_symlink_without_modifying_target(self):
        runtime = self.root / "runtime-alias"
        runtime.symlink_to(self.runtime, target_is_directory=True)
        with patch.object(deployment, "ROOT", self.root), patch.object(deployment, "PYFINDER_RUNTIME", runtime):
            with self.assertRaises(deployment.DeploymentError):
                deployment.setup()
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_data_action_is_explicit_and_forwarded(self):
        self.configure_service()
        with patch.object(deployment, "helper") as helper:
            with self.assertRaises(deployment.DeploymentError):
                deployment.dispatch(self.arguments("data", "shakemap"))
            helper.assert_not_called()
            deployment.dispatch(self.arguments("data", "shakemap", data_action="validate"))
            self.assertEqual(helper.call_args.args[3], ["validate", "--runtime", str(self.runtime)])

    def test_read_only_verify_never_delegates_native_verification(self):
        with patch.object(deployment, "preflight") as preflight, patch.object(deployment, "helper") as helper:
            deployment.dispatch(self.arguments("verify"))
            preflight.assert_called_once()
            helper.assert_not_called()

    def test_live_verification_requires_explicit_component(self):
        with patch.object(deployment, "helper") as helper:
            with self.assertRaises(deployment.DeploymentError):
                deployment.dispatch(self.arguments("verify", live=True))
            helper.assert_not_called()
            deployment.dispatch(self.arguments("verify", "pyfinder", live=True))
            self.assertEqual(helper.call_args.args[2], "verify-pyfinder-image.sh")

    def test_enabled_start_uses_existing_single_bind_launcher(self):
        self.configure_service()
        self.settings.update(
            PYFINDER_SHAKEMAP_ENABLED="true",
            PYFINDER_SHAKEMAP_URL="http://service.test:9010",
        )
        self.write_config()
        with patch.object(deployment, "helper") as helper:
            deployment.dispatch(self.arguments("start", "pyfinder"))
            helper.assert_called_once_with(
                self.settings, "pyfinder", "pyfinder", ["continuous"]
            )

    def test_disabled_caller_start_is_refused_before_commands(self):
        self.configure_service()
        with patch.object(deployment, "run") as run:
            with self.assertRaisesRegex(deployment.DeploymentError, "enable"):
                deployment.dispatch(self.arguments("start", "pyfinder"))
            run.assert_not_called()

    def test_external_runtime_is_rejected_before_any_component_command(self):
        external = self.root / "old-development-runtime"
        external.mkdir()
        self.settings["SHAKEMAP_RUNTIME_ROOT"] = str(external)
        self.write_config()
        with patch.object(deployment, "run") as run:
            with self.assertRaisesRegex(deployment.DeploymentError, "canonical runtime"):
                deployment.dispatch(self.arguments("start", "shakemap"))
            run.assert_not_called()
        self.assertEqual(list(external.iterdir()), [])

    def test_environment_has_only_reviewed_adapter_settings(self):
        self.configure_service()
        with patch.dict(os.environ, {"PYFINDER_SHAKEMAP_ENABLED": "true",
                                     "PYFINDER_SHAKEMAP_INPUT_HOST_DIRECTORY": "/unreviewed"}):
            environment = deployment.environment(self.settings)
        self.assertEqual(environment["PYFINDER_SHAKEMAP_ENABLED"], "false")
        self.assertNotIn("PYFINDER_SHAKEMAP_INPUT_HOST_DIRECTORY", environment)

    def test_optional_email_path_preserves_legacy_or_explicit_disabled_selection(self):
        self.assertNotIn("PYFINDER_ALERT_CONFIG", deployment.load_settings(self.config))
        with patch.dict(os.environ, {"PYFINDER_ALERT_CONFIG": "/ambient/private"}):
            self.assertNotIn("PYFINDER_ALERT_CONFIG", deployment.environment(self.settings))
        self.settings["PYFINDER_ALERT_CONFIG"] = ""
        self.write_config()
        loaded = deployment.load_settings(self.config)
        self.assertEqual(deployment.environment(loaded)["PYFINDER_ALERT_CONFIG"], "")

    def test_email_path_uses_existing_parent_mount_without_reading_secrets(self):
        target = self.runtime / "pyfinder/config/email.json"
        target.parent.mkdir(parents=True)
        target.write_text("deliberately not parsed by deployment")
        self.settings["PYFINDER_ALERT_CONFIG"] = "/home/sysop/runtime/pyfinder/config/email.json"
        self.write_config()
        self.assertEqual(deployment.load_settings(self.config), self.settings)
        for value in ("relative.json", "/outside/email.json", "/home/sysop/runtime/pyfinder/../secret", "/home/sysop/runtime/pyfinder/missing.json"):
            self.settings["PYFINDER_ALERT_CONFIG"] = value
            self.write_config()
            with self.assertRaises(deployment.DeploymentError):
                deployment.load_settings(self.config)

    def test_read_only_http_json(self):
        paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ready": true}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            result = deployment.get_json(f"http://127.0.0.1:{server.server_port}/healthz")
        finally:
            server.shutdown()
            worker.join()
            server.server_close()
        self.assertEqual(result, {"ready": True})
        self.assertEqual(paths, ["/healthz"])

    def preflight_records(self):
        """Describe exact consolidated mounts without contacting Docker."""
        self.configure_service()
        for name in ("state", "logs", "runs", "playbacks"):
            (self.runtime / "pyfinder" / name).mkdir(parents=True, exist_ok=True)

        parent = {"Type": "bind", "Source": str(self.runtime),
                  "Destination": "/home/sysop/runtime", "RW": True}
        service = {
            "Image": "image-id",
            "Mounts": [parent.copy()],
            "State": {"Running": True},
        }
        for name in ("global", "regional", "test"):
            service["Mounts"].append({
                "Type": "bind", "Source": str(self.runtime / "shakemap/data" / name),
                "Destination": f"/home/sysop/runtime/shakemap/data/{name}", "RW": False,
            })
        caller = {
            "Image": "image-id",
            "Mounts": [parent.copy()],
            "State": {"Running": True},
            "Config": {
                "Env": [f"{key}={self.settings[key]}" for key in deployment.APPLICATION_KEYS],
            },
        }
        return [{"Id": "image-id"}, service, {"Id": "image-id"}, caller]

    def check_preflight(self, records):
        with patch.object(deployment, "get_json", side_effect=[
            {"ready": True}, {"configurations": ["global"]},
        ]), patch.object(deployment, "inspect", side_effect=records), \
                patch.object(deployment, "helper") as helper:
            try:
                deployment.preflight(self.settings)
            finally:
                helper.assert_not_called()

    def test_preflight_accepts_enabled_caller_with_only_common_parent_bind(self):
        self.settings["PYFINDER_SHAKEMAP_ENABLED"] = "true"
        self.check_preflight(self.preflight_records())

    def test_preflight_rejects_wrong_source_extra_bind_or_writable_service_data(self):
        for defect in ("source", "extra-input", "service-data-rw", "missing-overlay"):
            records = self.preflight_records()
            service, caller = records[1], records[3]
            if defect == "source":
                caller["Mounts"][0]["Source"] = str(self.root / "old-runtime")
            elif defect == "extra-input":
                caller["Mounts"].append({
                    "Type": "bind", "Source": str(self.runtime / "shakemap/data/inputs"),
                    "Destination": deployment.INPUT_TARGET, "RW": True,
                })
            elif defect == "service-data-rw":
                service["Mounts"][1]["RW"] = True
            else:
                service["Mounts"].pop()
            with self.subTest(defect=defect), self.assertRaisesRegex(
                deployment.DeploymentError, "mounts"
            ):
                self.check_preflight(records)

    def test_preflight_rejects_stopped_containers_without_lifecycle_mutation(self):
        # A healthy HTTP response can outlive or come from another container.
        # Require the inspected canonical owner itself to be running as well.
        for index, name in ((1, "shakemap-docker"), (3, "pyfinder-docker")):
            records = self.preflight_records()
            records[index]["State"]["Running"] = False
            with self.subTest(container=name), patch.object(deployment, "run") as run:
                with self.assertRaisesRegex(
                    deployment.DeploymentError, name + ": canonical container is not running"
                ):
                    self.check_preflight(records)
                run.assert_not_called()

    def test_preflight_refuses_stale_image_without_lifecycle_mutation(self):
        records = self.preflight_records()
        records[3]["Image"] = "old-image"
        with self.assertRaisesRegex(deployment.DeploymentError, "stale image"):
            self.check_preflight(records)


if __name__ == "__main__":
    unittest.main()
