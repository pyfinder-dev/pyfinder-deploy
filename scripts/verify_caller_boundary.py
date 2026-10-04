"""Finite installed-caller checks with an explicit optional synthetic calculation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from uuid import uuid4

import deployment
import calculation_fixture


CONTAINER = "pyfinder-docker"
IMAGE = "pyfinder:dev"
LABEL = "io.pyfinder.verification"
OWNER = "caller-boundary"
BASE = "ghcr.io/sceylan/finder-base:gmt5"
PYTHON = "/opt/python-3.12/bin/python3.12"
MODULES = (
    "cli", "runtime", "start_monitoring", "findermanager", "pyfinderconfig",
    "services.scheduler", "services.database", "services.eventtracker",
    "services.shakemap_settings", "services.shakemap_client",
    "services.shakemap_inputs", "services.shakemap_workflow", "utils.shakemap",
)

# This is verification logic, sent on stdin. No application source or host
# environment is mounted into the image, so a missing installed module cannot
# accidentally be supplied by the development checkout.
CONTAINER_PROBE = r'''
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import tempfile
import sqlite3
from unittest.mock import patch


def installed_module_origins(package, names):
    """Require normal installed imports and report the code actually exercised."""
    assert "site-packages" in package.parts, "application not normally installed"
    origins = {}
    for name in names:
        module = importlib.import_module("pyfinder." + name)
        source = Path(module.__file__).resolve()
        assert source.is_relative_to(package), "module outside installed package"
        origins[name] = str(source)
    return origins


assert (os.geteuid(), os.getegid()) == (1000, 1000), "wrong runtime identity"
assert platform.python_version() == context["python_version"], "wrong Python version"
assert Path.cwd() == Path("/home/sysop"), "unexpected working directory"

# ParamWS logging is an import-time behavior. Keep that log in disposable
# container storage and forbid database/subprocess/SMTP use during all imports.
real_connect = sqlite3.connect

def guarded_connect(database, *arguments, **keywords):
    expected = context.get("calculation_workspace")
    if expected is None or keywords.get("uri"):
        raise AssertionError("database access forbidden")
    requested = Path(database)
    allowed = Path(expected) / "workflow.sqlite"
    if requested != allowed or requested.resolve() != allowed:
        raise AssertionError("database outside owned fixture workspace")
    return real_connect(database, *arguments, **keywords)

with tempfile.TemporaryDirectory(prefix="pyfinder-boundary-") as temporary:
    os.environ["PARAMWS_LOG_FILE"] = str(Path(temporary) / "paramws.log")
    with patch("sqlite3.connect", side_effect=guarded_connect), \
         patch("subprocess.Popen", side_effect=AssertionError("subprocess forbidden")), \
         patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden")):
        import pyfinder
        package = Path(pyfinder.__file__).resolve().parent
        origins = installed_module_origins(package, context["modules"])

        from pyfinder.pyfinderconfig import pyfinderconfig
        from pyfinder.services.shakemap_settings import continuous_shakemap_configuration
        from pyfinder.services.shakemap_client import ShakeMapClient
        settings = continuous_shakemap_configuration(pyfinderconfig)["shakemap"]
        assert settings["service-enabled"] is False, "probe requires disabled integration"
        inputs = Path(settings["input-directory"])
        assert inputs == Path("/home/sysop/runtime/shakemap/data/inputs")
        assert (inputs / context["host_marker"]).read_text() == context["nonce"]

        # Exclusive creation proves this container's UID can write the actual
        # shared directory. The host will compare these bytes and remove only
        # this uniquely owned marker after the finite container exits.
        with (inputs / context["caller_marker"]).open("x") as stream:
            stream.write(context["nonce"])

        client = ShakeMapClient(settings["service-url"], timeout=10)
        health = client.health()
        assert health["ready"] is True, "service not ready"
        configurations = client.configurations()
        assert settings["configuration"] in configurations["configurations"], "selected configuration absent"

        # Image verification owns build-record consistency. This network probe
        # reports installed versions and keeps the containment checks needed to
        # prove its imports came from the image, not a host checkout.
        versions = {name: importlib.metadata.version(name)
                    for name in ("pyfinder", "paramws-clients")}
        import paramws
        paramws_root = Path(paramws.__file__).resolve().parent
        assert "site-packages" in paramws_root.parts, "dependency not normally installed"
        for distribution, module_root in (
            ("pyfinder", package),
            ("paramws-clients", paramws_root),
        ):
            distribution_root = Path(importlib.metadata.distribution(distribution).locate_file("")).resolve()
            assert module_root.is_relative_to(distribution_root)

        result = {
            "uid": os.geteuid(), "gid": os.getegid(),
            "python_version": platform.python_version(), "versions": versions,
            "installed_package": str(package), "installed_paramws": str(paramws_root),
            "installed_modules": origins,
            "selected_configuration": settings["configuration"],
            "health": health, "configuration_listed": True,
            "shared_input_read_write": True, "integration_enabled": False,
        }
        if context.get("calculation_fixture") is not None:
            result["calculation"] = run_calculation(context, client)
        print("PYFINDER_CALLER_PROBE=" + json.dumps(result, sort_keys=True))
'''


def command(arguments, *, timeout=30, input=None, env=None):
    """Bound every Docker command and keep unreviewed output out of diagnostics."""
    return subprocess.run(arguments, input=input, env=env, capture_output=True,
                          text=True, timeout=timeout, check=False)


def present():
    result = command(["docker", "container", "ls", "--all", "--filter",
                      "name=^/pyfinder-docker$", "--format", "{{.Names}}"])
    if result.returncode:
        raise deployment.DeploymentError("Could not establish canonical caller presence")
    return bool(result.stdout.strip())


def image_context():
    result = command(["docker", "image", "inspect", IMAGE])
    if result.returncode:
        raise deployment.DeploymentError("Canonical PyFinder image is unavailable")
    try:
        image = json.loads(result.stdout)[0]
        configuration = image["Config"]
        labels = configuration["Labels"]
        valid = (
            re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"])
            and image["Os"] == "linux" and image["Architecture"] == "amd64"
            and configuration["User"] == "1000:1000"
            and configuration["Entrypoint"] == ["/usr/local/bin/pyfinder-entrypoint"]
            and configuration["Cmd"] == ["continuous"]
            and labels["org.opencontainers.image.base.name"] == BASE
            and re.fullmatch(r"3\.12\.[0-9]+", labels["io.pyfinder.python.version"])
        )
        if not valid:
            raise ValueError
    except (ValueError, KeyError, TypeError, IndexError):
        raise deployment.DeploymentError("Image identity/entrypoint/platform differs from the supported caller") from None
    return image["Id"], labels["io.pyfinder.python.version"]


def cleanup_container(cidfile):
    """Remove only this probe's exact recorded ID if --rm did not finish."""
    if not present():
        return
    if not cidfile.is_file():
        raise deployment.DeploymentError("Caller container remains without this probe's ID; left untouched")
    identity = cidfile.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise deployment.DeploymentError("Probe container ID is invalid; remaining container left untouched")
    inspected = command(["docker", "container", "inspect", "--format",
                         '{{.Id}}|{{index .Config.Labels "io.pyfinder.verification"}}', CONTAINER])
    if inspected.returncode or inspected.stdout.strip() != f"{identity}|{OWNER}":
        raise deployment.DeploymentError("Probe container ownership differs; remaining container left untouched")
    removed = command(["docker", "container", "rm", "--force", identity])
    if removed.returncode:
        raise deployment.DeploymentError("Could not remove the probe's own container")


def cleanup_marker(path, nonce):
    """Never remove a preexisting/replaced entry merely because its name matches."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or path.read_text() != nonce:
        raise deployment.DeploymentError("Probe marker ownership changed; entry left untouched")
    path.unlink()


def verify(settings, evidence, *, fixture=None, event_id=None, expected_outcome="SUCCESS"):
    """Run one disposable canonical caller; retain evidence outside the runtime."""
    runtime = deployment.service_runtime(settings)
    if (fixture is None) != (event_id is None):
        raise deployment.DeploymentError("Calculation fixture and event ID must be supplied together")
    if fixture is not None:
        calculation_fixture.validate_fixture(fixture, event_id)
        deployment.absolute_directory(str(runtime / "pyfinder/playbacks"), "Experimental workspace root")
        calculation_root = runtime / "pyfinder/playbacks" / event_id
        if calculation_root.exists() or calculation_root.is_symlink():
            raise deployment.DeploymentError("Experimental fixture workspace already exists; choose a fresh ID")
    inputs = deployment.absolute_directory(str(runtime / "shakemap/data/inputs"), "Shared inputs")
    if settings["PYFINDER_SHAKEMAP_ENABLED"] != "false" or not settings["PYFINDER_SHAKEMAP_URL"]:
        raise deployment.DeploymentError("Probe requires disabled integration and an explicit caller URL")
    if (not evidence.is_absolute() or evidence.parent.resolve(strict=True) != evidence.parent
            or evidence.exists() or evidence.is_symlink() or evidence.is_relative_to(runtime)):
        raise deployment.DeploymentError("Use a fresh absolute evidence directory outside runtime with an existing resolved parent")
    if present():
        raise deployment.DeploymentError("Canonical pyfinder-docker exists; preserve it and arrange explicit replacement first")
    image_id, python_version = image_context()
    # Probe the installed image's capabilities. Local uncommitted edits do not
    # define an operator's installed release and must not gate verification.
    modules = list(MODULES)

    evidence.mkdir(mode=0o700)
    nonce = uuid4().hex
    host_marker = inputs / (".pyfinder-boundary-" + nonce + "-host")
    caller_marker = inputs / (".pyfinder-boundary-" + nonce + "-caller")
    cidfile = evidence / "container.cid"
    context = {"python_version": python_version, "modules": modules,
               "nonce": nonce, "host_marker": host_marker.name,
               "caller_marker": caller_marker.name}
    if fixture is not None:
        modules.extend(("finderutils", "eventcontext"))
        context.update(
            calculation_fixture=fixture, event_id=event_id,
            host_service=str(runtime / "shakemap"),
            calculation_workspace=f"/home/sysop/runtime/pyfinder/playbacks/{event_id}/shakemap-verification",
        )
    # JSON is embedded as a Python string literal, never as shell code or an
    # application source mount. Only probe context and verification code travel.
    fixture_code = ""
    if fixture is not None:
        fixture_code = Path(calculation_fixture.__file__).read_text() + "\n"
    program = "import json\ncontext = json.loads(" + repr(json.dumps(context)) + ")\n" + fixture_code + CONTAINER_PROBE
    arguments = ["docker", "run", "--rm", "--interactive", "--name", CONTAINER,
                 "--cidfile", str(cidfile), "--label", f"{LABEL}={OWNER}",
                 "--platform", "linux/amd64", "--pull=never", "--user", "1000:1000",
                 "--mount", f"type=bind,source={runtime},target=/home/sysop/runtime",
                 "--workdir", "/home/sysop", "--entrypoint", PYTHON]
    for key in deployment.APPLICATION_KEYS:
        arguments.extend(["--env", key])
    arguments.extend([image_id, "-I", "-"])

    result = None
    failure = None
    cleanup_errors = []
    phase = "creating exclusive host marker"
    host_created = False
    launched = False
    try:
        with host_marker.open("x") as stream:
            host_created = True
            stream.write(nonce)
        host_marker.chmod(0o644)
        if caller_marker.exists() or caller_marker.is_symlink():
            raise deployment.DeploymentError("Caller marker already exists; left untouched")
        launched = True
        process_deadline = 780 if fixture is not None else 120
        phase = f"running finite installed caller ({process_deadline} second process deadline)"
        completed = command(arguments, timeout=process_deadline, input=program, env=deployment.environment(settings))
        (evidence / "stdout.log").write_text(completed.stdout)
        (evidence / "stderr.log").write_text(completed.stderr)
        if completed.returncode:
            raise deployment.DeploymentError(f"Finite caller probe exited {completed.returncode}; inspect protected evidence")
        phase = "validating returned evidence and host-visible caller marker"
        rows = [line.split("=", 1)[1] for line in completed.stdout.splitlines()
                if line.startswith("PYFINDER_CALLER_PROBE=")]
        if len(rows) != 1:
            raise deployment.DeploymentError("Finite caller probe produced no unique verified result")
        result = json.loads(rows[0])
        if caller_marker.is_symlink() or caller_marker.read_text() != nonce:
            raise deployment.DeploymentError("Caller marker is not visible through the expected host inputs")
        result.update(image_id=image_id, runtime_root=str(runtime), host_shared_bytes_verified=True)
        if fixture is not None:
            calculation = result["calculation"]
            calculation["expected_outcome"] = expected_outcome
            if calculation["classification"] != "NATIVE_TERMINAL":
                raise deployment.DeploymentError("Fixture did not produce validated terminal evidence; inspect its retained workspace")
            if calculation["outcome"] != expected_outcome:
                raise deployment.DeploymentError(f"Native fixture outcome {calculation['outcome']} differs from expected {expected_outcome}")
    except BaseException as error:
        failure = error
    finally:
        # A failed/timeout probe must not leave a service-like container behind.
        # Cleanup errors remain visible without losing the original failure.
        operations = []
        if launched:
            operations.append(lambda: cleanup_container(cidfile))
        if host_created:
            operations.append(lambda: cleanup_marker(host_marker, nonce))
        if launched:
            operations.append(lambda: cleanup_marker(caller_marker, nonce))
        for operation in operations:
            try:
                operation()
            except BaseException as error:
                detail = str(error) if isinstance(error, deployment.DeploymentError) else type(error).__name__
                cleanup_errors.append(detail)
                if failure is None:
                    failure = error
                    phase = "cleaning this probe's owned resources"
                else:
                    failure.add_note(f"Cleanup also failed: {type(error).__name__}: {detail}")
        diagnostic = None
        if failure is not None:
            diagnostic = {
                "type": type(failure).__name__, "phase": phase,
                "message": str(failure) if isinstance(failure, deployment.DeploymentError)
                else "Operation failed; inspect phase and protected process logs if present",
            }
        report = {"passed": failure is None, "result": result,
                  "failure": diagnostic, "cleanup_errors": cleanup_errors}
        (evidence / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if failure is not None:
        raise failure
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=deployment.ROOT / "deployment.env")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--calculation-fixture", type=Path,
                        help="Explicitly submit one synthetic native calculation from this JSON fixture")
    parser.add_argument("--event-id", help="Fresh caller-owned pyfinder-verification-..._t00000 ID")
    parser.add_argument("--expect-native", choices=("SUCCESS", "FAILED"), default="SUCCESS",
                        help="Assert this native outcome; FAILED never means deployment readiness")
    arguments = parser.parse_args()
    if (arguments.calculation_fixture is None) != (arguments.event_id is None):
        parser.error("--calculation-fixture and --event-id must be supplied together")
    if arguments.calculation_fixture is None and arguments.expect_native != "SUCCESS":
        parser.error("--expect-native requires --calculation-fixture")
    expected_environment = deployment.ROOT.parent / ".venv"
    if Path(sys.prefix).resolve() != expected_environment.resolve():
        parser.error("Activate the existing .venv in the parent of this checkout; do not use system Python")
    try:
        fixture = None if arguments.calculation_fixture is None else json.loads(arguments.calculation_fixture.read_text())
        verify(deployment.load_settings(arguments.config), arguments.evidence,
               fixture=fixture, event_id=arguments.event_id, expected_outcome=arguments.expect_native)
    except (deployment.DeploymentError, OSError, ValueError, subprocess.SubprocessError) as error:
        detail = str(error) if isinstance(error, deployment.DeploymentError) else type(error).__name__
        print(f"verify-caller: {detail}; inspect the protected evidence and configuration", file=sys.stderr)
        return 1
    print(f"Finite installed caller checks passed; evidence: {arguments.evidence}")
    if arguments.calculation_fixture is None:
        print("No production workflow or scientific calculation ran; the canonical caller is absent.")
    else:
        print("Explicit fixture outcome matched; inspect retained evidence. No production workflow ran and no deployment readiness is claimed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
