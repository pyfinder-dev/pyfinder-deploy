"""Small host-side deployment helpers; scientific workflows stay in their owners."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
PYFINDER_RUNTIME = ROOT / "runtime"
INPUT_TARGET = "/home/sysop/runtime/shakemap/data/inputs"
APPLICATION_KEYS = (
    "PYFINDER_SHAKEMAP_ENABLED",
    "PYFINDER_SHAKEMAP_URL",
    "PYFINDER_SHAKEMAP_INPUT_DIRECTORY",
    "PYFINDER_SHAKEMAP_CONFIGURATION",
    "PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS",
    "PYFINDER_SHAKEMAP_OVERWRITE",
)
OPTIONAL_KEYS = {"PYFINDER_ALERT_CONFIG"}
KEYS = set(APPLICATION_KEYS) | {
    "PYFINDER_REPOSITORY", "SHAKEMAP_REPOSITORY", "SHAKEMAP_RUNTIME_ROOT",
    "SHAKEMAP_PORT", "SHAKEMAP_MAX_CONCURRENT",
}


class DeploymentError(Exception):
    """An actionable operator error whose message contains no setting values."""


def absolute_directory(value, name, *, required=True):
    if not value and not required:
        return None

    path = Path(value)
    if not value or not path.is_absolute() or path.resolve() != path:
        raise DeploymentError(f"{name}: use an absolute resolved directory path")
    if not path.is_dir():
        raise DeploymentError(f"{name}: directory does not exist; inspect the intended host path")

    return path


def read_settings(path):
    """Read literal values without interpreting shell quotes or substitutions."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeploymentError("Local configuration cannot be read; run setup or supply --config") from exc

    settings = {}
    for number, line in enumerate(contents.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in KEYS | OPTIONAL_KEYS or key in settings:
            raise DeploymentError(f"Configuration line {number}: unknown, duplicate, or malformed setting")
        if any(character in value for character in "$`;|&<>\x00\r\n") or value != value.strip():
            raise DeploymentError(f"Configuration line {number}: use a literal value without shell syntax or edge whitespace")
        settings[key] = value

    return settings


def settings_problems(settings):
    """Collect independent setting errors without exposing supplied values.

    Mutating helpers still reject the first problem through load_settings.
    The read-only check uses the same rules to explain incomplete setup at once.
    """
    problems = []
    for key in sorted(KEYS - settings.keys()):
        problems.append((key, "required setting is missing"))

    for key in ("PYFINDER_REPOSITORY", "SHAKEMAP_REPOSITORY"):
        if key not in settings:
            continue
        try:
            absolute_directory(settings[key], key)
        except DeploymentError as error:
            problems.append((key, str(error)))

    if "SHAKEMAP_RUNTIME_ROOT" in settings:
        try:
            service_runtime(settings)
        except DeploymentError as error:
            problems.append(("SHAKEMAP_RUNTIME_ROOT", str(error)))

    alert_path = settings.get("PYFINDER_ALERT_CONFIG")
    if alert_path:
        path = Path(alert_path)
        caller_root = Path("/home/sysop/runtime/pyfinder")
        if not path.is_absolute() or ".." in path.parts or path == caller_root or not path.is_relative_to(caller_root):
            problems.append(("PYFINDER_ALERT_CONFIG", "use a file inside /home/sysop/runtime/pyfinder or empty to disable"))
        else:
            host_path = PYFINDER_RUNTIME / path.relative_to("/home/sysop/runtime")
            if host_path.resolve() != host_path or not host_path.is_file():
                problems.append(("PYFINDER_ALERT_CONFIG", "mapped file is missing or uses symlinks; place the existing separate email configuration in caller runtime"))

    for key in ("PYFINDER_SHAKEMAP_ENABLED", "PYFINDER_SHAKEMAP_OVERWRITE"):
        if key in settings and settings[key] not in {"true", "false"}:
            problems.append((key, "use exactly true or false"))
    for key in ("SHAKEMAP_PORT", "SHAKEMAP_MAX_CONCURRENT"):
        value = settings.get(key)
        if value is None:
            continue
        if not value.isascii() or not value.isdigit() or int(value) < 1:
            problems.append((key, "use a positive integer"))
        elif key == "SHAKEMAP_PORT" and int(value) > 65535:
            problems.append((key, "use an integer from 1 through 65535"))

    key = "PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS"
    if key in settings:
        try:
            timeout = float(settings[key])
        except ValueError:
            timeout = math.nan
        if not math.isfinite(timeout) or timeout <= 0:
            problems.append((key, "use a positive finite number"))
    key = "PYFINDER_SHAKEMAP_CONFIGURATION"
    if key in settings and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", settings[key]):
        problems.append((key, "use an explicit service configuration name"))
    key = "PYFINDER_SHAKEMAP_INPUT_DIRECTORY"
    if key in settings and settings[key] != INPUT_TARGET:
        problems.append((key, "retain the documented canonical container input path"))

    # URLs are checked even when integration is disabled. Their contents never
    # enter diagnostics because malformed values may contain credentials.
    url = settings.get("PYFINDER_SHAKEMAP_URL", "")
    if url:
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and parsed.username is None and parsed.password is None
                     and not parsed.query and not parsed.fragment
                     and parsed.port != 0 and "\\" not in url
                     and not any(character.isspace() or ord(character) < 32
                                 or ord(character) == 127 for character in url))
        except ValueError:
            valid = False
        if not valid:
            problems.append(("PYFINDER_SHAKEMAP_URL", "use an absolute HTTP(S) URL without credentials, query, or fragment"))
    return problems


def load_settings(path):
    """Require complete, valid settings before an operational action."""
    settings = read_settings(path)
    problems = settings_problems(settings)
    if problems:
        key, reason = problems[0]
        raise DeploymentError(f"{key}: {reason}")
    return settings


def component_root(settings, component):
    return Path(settings[f"{component.upper()}_REPOSITORY"])


def service_runtime(settings):
    """Require the approved common parent without adopting another data tree.

    Both canonical containers mount this parent at /home/sysop/runtime. Keeping
    the host identity equal is what makes the existing caller input path refer
    to the service's actual files; no additional input bind is necessary.
    """
    runtime = absolute_directory(settings["SHAKEMAP_RUNTIME_ROOT"], "SHAKEMAP_RUNTIME_ROOT")
    if runtime != PYFINDER_RUNTIME:
        raise DeploymentError(
            "SHAKEMAP_RUNTIME_ROOT: use this deployment repository's canonical runtime; "
            "external service storage is not supported and no data was moved"
        )
    return runtime


def service_arguments(settings):
    return ["--runtime-root", str(service_runtime(settings)),
            "--port", settings["SHAKEMAP_PORT"],
            "--max-concurrent", settings["SHAKEMAP_MAX_CONCURRENT"]]


def environment(settings):
    # Configuration is complete and authoritative. An unrelated shell variable
    # must not quietly enable integration or replace a reviewed endpoint.
    result = os.environ.copy()
    for key in APPLICATION_KEYS:
        result[key] = settings[key]
    result.pop("PYFINDER_SHAKEMAP_INPUT_HOST_DIRECTORY", None)
    result.pop("PYFINDER_ALERT_CONFIG", None)
    if "PYFINDER_ALERT_CONFIG" in settings:
        result["PYFINDER_ALERT_CONFIG"] = settings["PYFINDER_ALERT_CONFIG"]
    return result


def run(command, *, cwd, env=None, capture=False):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True,
                                capture_output=capture, check=False)
    except OSError as exc:
        raise DeploymentError("Required component helper or Docker command could not be executed") from exc
    if result.returncode:
        raise DeploymentError(f"Component command failed with exit status {result.returncode}; inspect its diagnostics")
    return result.stdout if capture else None


def helper(settings, component, filename, arguments=(), *, capture=False):
    root = component_root(settings, component)
    return run([str(root / "scripts" / filename), *arguments], cwd=root,
               env=environment(settings), capture=capture)


def setup(destination=None):
    """Create only missing caller-owned directories and local configuration."""
    paths = [PYFINDER_RUNTIME, PYFINDER_RUNTIME / "pyfinder"]
    paths += [PYFINDER_RUNTIME / "pyfinder" / name
              for name in ("state", "logs", "runs", "playbacks")]
    for path in paths:
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise DeploymentError("A required PyFinder runtime directory is a symlink or non-directory; inspect it before setup")

    destination = destination if destination is not None else ROOT / "deployment.env"
    if not destination.parent.is_dir():
        raise DeploymentError("Local settings parent directory does not exist; create it explicitly before setup")
    try:
        with destination.open("x", encoding="utf-8") as stream:
            os.chmod(destination, 0o600)
            stream.write((ROOT / "deployment.env.example").read_text(encoding="utf-8"))
    except FileExistsError:
        print("Existing deployment.env preserved.")
    for path in paths:
        path.mkdir(exist_ok=True)
    print("PyFinder directories prepared; no ownership was changed. Review deployment.env before other commands.")


def get_json(url):
    try:
        with urlopen(url, timeout=5) as response:
            return json.load(response)
    except (OSError, ValueError, HTTPError, URLError) as exc:
        raise DeploymentError("ShakeMap read-only HTTP check failed; inspect the service address and health") from exc


def inspect(resource, name):
    output = run(["docker", resource, "inspect", name], cwd=ROOT, capture=True)
    try:
        records = json.loads(output)
        if len(records) != 1 or not isinstance(records[0], dict):
            raise ValueError
        return records[0]
    except (ValueError, TypeError, IndexError) as exc:
        raise DeploymentError("Docker inspection returned an unexpected response") from exc


def container_problems(settings, component, image, container):
    """Share canonical deployment wiring checks between verify and check."""
    problems = []
    if container.get("Image") != image.get("Id"):
        problems.append("stale image; deliberate container replacement is required")
    runtime = PYFINDER_RUNTIME
    expected = {(str(runtime), "/home/sysop/runtime", True)}
    if component == "shakemap":
        expected |= {(str(runtime / "shakemap/data" / name),
                      f"/home/sysop/runtime/shakemap/data/{name}", False)
                     for name in ("global", "regional", "test")}
    mounts = {(item.get("Source"), item.get("Destination"), item.get("RW"))
              for item in container.get("Mounts", []) if item.get("Type") == "bind"}
    if mounts != expected or len(container.get("Mounts", [])) != len(expected):
        problems.append("runtime mounts do not match reviewed settings")
    if component == "pyfinder":
        actual = dict(item.split("=", 1) for item in container.get("Config", {}).get("Env", []) if "=" in item)
        for key in (*APPLICATION_KEYS, *OPTIONAL_KEYS):
            if actual.get(key) != settings.get(key):
                problems.append(f"{key} differs")
    return problems


def preflight(settings):
    """Inspect wiring only; do not run native verification or start processes."""
    runtime = service_runtime(settings)
    absolute_directory(str(runtime / "shakemap/data/inputs"), "Shared ShakeMap inputs")
    for name in ("state", "logs", "runs", "playbacks"):
        absolute_directory(str(PYFINDER_RUNTIME / "pyfinder" / name), "PyFinder runtime")

    selected = settings["PYFINDER_SHAKEMAP_CONFIGURATION"]
    host_url = f"http://127.0.0.1:{settings['SHAKEMAP_PORT']}"
    health = get_json(host_url + "/healthz")
    configurations = get_json(host_url + "/configurations")
    if not isinstance(health, dict) or health.get("ready") is not True:
        raise DeploymentError("ShakeMap does not report ready; inspect component status and finalization")
    if not isinstance(configurations, dict) or selected not in configurations.get("configurations", []):
        raise DeploymentError("The selected ShakeMap configuration is unavailable; no fallback is applied")

    for component, image_name, container_name in (
        ("shakemap", "shakemap-docker:latest", "shakemap-docker"),
        ("pyfinder", "pyfinder:dev", "pyfinder-docker"),
    ):
        image = inspect("image", image_name)
        container = inspect("container", container_name)

        # Matching mounts and image bytes do not establish a running caller.
        # Strict verification observes both owners and never starts either one.
        if container.get("State", {}).get("Running") is not True:
            raise DeploymentError(
                f"{container_name}: canonical container is not running; no container was changed"
            )

        problems = container_problems(settings, component, image, container)
        if problems:
            raise DeploymentError(f"{container_name}: {problems[0]}; no container was changed")
        print(f"{container_name}: inspected image identity and runtime mounts.")

    print("Host preflight passed. Caller-network reachability, UID write access, installed adapter modules, and native/regional execution remain separate checks.")


def dispatch(args):
    if args.action == "check":
        # Import only the small diagnostic helper. Scientific application
        # startup, log handlers and database owners are never constructed here.
        from check_deployment import check
        return check(sys.modules[__name__], args.config, json_output=args.json)
    if args.action == "setup":
        setup(args.config)
        return
    settings = load_settings(args.config)
    component = args.component
    if args.action in {"build", "data", "finalize", "start", "stop"} and component is None:
        raise DeploymentError("Select --component pyfinder or shakemap explicitly")

    if args.action == "build":
        if component == "shakemap":
            helper(settings, component, "build-shakemap-docker.sh")
        else:
            root = component_root(settings, component)
            run(["docker", "build", "--platform", "linux/amd64", "--tag", "pyfinder:dev", str(root)], cwd=root)
    elif args.action == "data":
        if component != "shakemap" or args.data_action is None:
            raise DeploymentError("Data operations require --component shakemap and an explicit --data-action")
        helper(settings, component, "manage-shakemap-data.sh",
               [args.data_action, "--runtime", str(service_runtime(settings))])
    elif args.action == "finalize":
        if component != "shakemap":
            raise DeploymentError("Finalization belongs to ShakeMap; use --component shakemap")
        helper(settings, component, "finalize-shakemap.sh", service_arguments(settings))
    elif args.action == "start":
        if component == "shakemap":
            helper(settings, component, "start-shakemap-docker.sh", service_arguments(settings))
        else:
            if settings["PYFINDER_SHAKEMAP_ENABLED"] != "true" or not settings["PYFINDER_SHAKEMAP_URL"]:
                raise DeploymentError("Review and enable the explicit ShakeMap integration settings before continuous deployment startup")
            absolute_directory(str(service_runtime(settings) / "shakemap/data/inputs"), "Shared ShakeMap inputs")
            # The common parent bind already exposes these inputs to the caller.
            # Its component helper retains ownership of image/env compatibility
            # and lifecycle; do not require an invented second mount interface.
            helper(settings, component, "pyfinder", ["continuous"])
    elif args.action == "stop":
        if component == "pyfinder":
            helper(settings, component, "pyfinder", ["stop"])
        else:
            helper(settings, component, "stop-shakemap-docker.sh")
    elif args.action == "status":
        run(["docker", "container", "ls", "--all", "--filter", "name=^/(pyfinder-docker|shakemap-docker)$",
             "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"], cwd=ROOT)
        print("Container state is not workflow or scientific readiness. Run verify for read-only wiring checks.")
    elif args.action == "verify":
        if not args.live:
            preflight(settings)
        elif component == "shakemap":
            helper(settings, component, "verify-shakemap-deployment.sh", service_arguments(settings))
        elif component == "pyfinder":
            helper(settings, component, "verify-pyfinder-image.sh")
        else:
            raise DeploymentError("Explicit --live verification requires --component pyfinder or shakemap")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "check accumulates read-only diagnostics for incomplete installations; "
            "verify requires both existing containers and checks wiring read-only. "
            "verify --live --component pyfinder creates an offline temporary caller; "
            "verify --live --component shakemap runs native verification and can "
            "change readiness or stop the service. Prefer make verify-image or "
            "make verify-native for these explicit workflows."
        ),
    )
    parser.add_argument("action", choices=("setup", "build", "data", "finalize", "start", "stop", "status", "check", "verify"))
    parser.add_argument("--config", type=Path, default=ROOT / "deployment.env")
    parser.add_argument("--component", choices=("pyfinder", "shakemap"))
    parser.add_argument("--data-action", choices=("inspect", "validate", "provision", "stage"))
    parser.add_argument("--live", action="store_true",
                        help="Run the selected component verifier with the side effects described below")
    parser.add_argument("--json", action="store_true",
                        help="Print the full structured check report instead of concise operator text")
    args = parser.parse_args()
    if args.json and args.action != "check":
        parser.error("--json belongs to check only")
    if args.live and args.action != "verify":
        parser.error("--live belongs to verify only")
    if args.data_action and args.action != "data":
        parser.error("--data-action belongs to data only")
    if sys.prefix == sys.base_prefix:
        parser.error("Activate the existing project virtual environment; do not use system Python")
    try:
        return dispatch(args)
    except DeploymentError as exc:
        print(f"deployment: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
