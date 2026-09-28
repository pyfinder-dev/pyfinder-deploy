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


def load_settings(path):
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

    if not KEYS.issubset(settings):
        raise DeploymentError("Configuration has missing settings; compare its keys with deployment.env.example")

    for key in ("PYFINDER_REPOSITORY", "SHAKEMAP_REPOSITORY"):
        absolute_directory(settings[key], key)
    service_runtime(settings)

    # Forward only a path into the existing caller bind, never credentials or
    # another mount. Absence keeps legacy discovery; empty explicitly disables.
    alert_path = settings.get("PYFINDER_ALERT_CONFIG")
    if alert_path:
        path = Path(alert_path)
        caller_root = Path("/home/sysop/runtime/pyfinder")
        if not path.is_absolute() or ".." in path.parts or path == caller_root or not path.is_relative_to(caller_root):
            raise DeploymentError("PYFINDER_ALERT_CONFIG: use a file inside /home/sysop/runtime/pyfinder or empty to disable")
        host_path = PYFINDER_RUNTIME / path.relative_to("/home/sysop/runtime")
        if host_path.resolve() != host_path or not host_path.is_file():
            raise DeploymentError("PYFINDER_ALERT_CONFIG: mapped file is missing or uses symlinks; place the existing separate email configuration in caller runtime")

    for key in ("PYFINDER_SHAKEMAP_ENABLED", "PYFINDER_SHAKEMAP_OVERWRITE"):
        if settings[key] not in {"true", "false"}:
            raise DeploymentError(f"{key}: use exactly true or false")
    for key in ("SHAKEMAP_PORT", "SHAKEMAP_MAX_CONCURRENT"):
        if not settings[key].isascii() or not settings[key].isdigit() or int(settings[key]) < 1:
            raise DeploymentError(f"{key}: use a positive integer")
    if int(settings["SHAKEMAP_PORT"]) > 65535:
        raise DeploymentError("SHAKEMAP_PORT: use an integer from 1 through 65535")

    try:
        timeout = float(settings["PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS"])
    except ValueError:
        timeout = math.nan
    if not math.isfinite(timeout) or timeout <= 0:
        raise DeploymentError("PYFINDER_SHAKEMAP_REQUEST_TIMEOUT_SECONDS: use a positive finite number")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", settings["PYFINDER_SHAKEMAP_CONFIGURATION"]):
        raise DeploymentError("PYFINDER_SHAKEMAP_CONFIGURATION: use an explicit service configuration name")
    if settings["PYFINDER_SHAKEMAP_INPUT_DIRECTORY"] != INPUT_TARGET:
        raise DeploymentError("PYFINDER_SHAKEMAP_INPUT_DIRECTORY: retain the documented canonical container input path")

    # Validate URLs even when disabled, without echoing credentials or other
    # accidental private content in an error. A missing URL remains a visible
    # setup task until the operator deliberately enables integration.
    url = settings["PYFINDER_SHAKEMAP_URL"]
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
            raise DeploymentError("PYFINDER_SHAKEMAP_URL: use an absolute HTTP(S) URL without credentials, query, or fragment")

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
        if container.get("Image") != image.get("Id"):
            raise DeploymentError(f"{container_name}: stale image; deliberate container replacement is required")
        mounts = {(item.get("Source"), item.get("Destination"), item.get("RW"))
                  for item in container.get("Mounts", []) if item.get("Type") == "bind"}
        if component == "shakemap":
            expected = {(str(runtime), "/home/sysop/runtime", True)}
            expected |= {(str(runtime / "shakemap/data" / name),
                          f"/home/sysop/runtime/shakemap/data/{name}", False)
                         for name in ("global", "regional", "test")}
        else:
            expected = {(str(PYFINDER_RUNTIME), "/home/sysop/runtime", True)}
        if mounts != expected or len(container.get("Mounts", [])) != len(expected):
            raise DeploymentError(f"{container_name}: runtime mounts do not match reviewed settings; no container was changed")
        if component == "pyfinder":
            actual = dict(item.split("=", 1) for item in container.get("Config", {}).get("Env", []) if "=" in item)
            for key in (*APPLICATION_KEYS, *OPTIONAL_KEYS):
                if actual.get(key) != settings.get(key):
                    raise DeploymentError(f"{container_name}: {key} differs; no setting was applied")
        print(f"{container_name}: inspected image identity and runtime mounts.")

    print("Host preflight passed. Caller-network reachability, UID write access, installed adapter modules, and native/regional execution remain separate checks.")


def dispatch(args):
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "build", "data", "finalize", "start", "stop", "status", "verify"))
    parser.add_argument("--config", type=Path, default=ROOT / "deployment.env")
    parser.add_argument("--component", choices=("pyfinder", "shakemap"))
    parser.add_argument("--data-action", choices=("inspect", "validate", "provision", "stage"))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live and args.action != "verify":
        parser.error("--live belongs to verify only")
    if args.data_action and args.action != "data":
        parser.error("--data-action belongs to data only")
    if sys.prefix == sys.base_prefix:
        parser.error("Activate the existing project virtual environment; do not use system Python")
    try:
        dispatch(args)
    except DeploymentError as exc:
        print(f"deployment: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
