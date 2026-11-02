"""Read-only deployment diagnostics, composed from component-owned checks."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import quote



def aggregate(statuses):
    """Unknown required evidence cannot turn an otherwise quiet check green."""
    for status in ("blocked", "unverified", "degraded"):
        if status in statuses:
            return status
    return "usable"


def caller_settings(deployment, settings):
    """Ask PyFinder to validate its own settings, without application startup."""
    root = Path(settings["PYFINDER_REPOSITORY"])
    command = [sys.executable, "-B", "-m", "pyfinder.services.shakemap_settings", "--check",
               "--input-directory", str(deployment.PYFINDER_RUNTIME / "shakemap/data/inputs")]
    result = subprocess.run(command, cwd=root, env=deployment.environment(settings),
                            text=True, capture_output=True, check=False, timeout=20)
    # Component stderr may contain incidental import or dependency diagnostics.
    # Do not repeat it: only the documented, deliberately sanitized JSON crosses
    # this boundary, and a missing/newer interface remains explicitly unknown.
    if result.returncode not in (0, 1):
        raise ValueError("caller checker unavailable")
    report = json.loads(result.stdout)
    if not isinstance(report, dict) or report.get("status") not in {"ready", "blocked"}:
        raise ValueError("caller checker returned an unsupported report")
    return report


def backlog(path, *, caller_running):
    """Inspect a closed queue without creating SQLite journal/lock files.

    An active owner or WAL can contain newer data than the main database. Leave
    that state unknown rather than use immutable mode to report a stale count.
    """
    if path.is_symlink():
        return {"status": "blocked", "reason": "Operational database path is a symlink; inspect its intended location"}
    if not path.exists():
        return {"status": "usable", "reason": "No operational database exists; startup initializes an empty queue"}
    if caller_running is not False or any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        return {"status": "unverified", "reason": "Queue may be active or have uncheckpointed state; no SQLite files were changed"}
    if path.is_symlink() or not path.is_file():
        return {"status": "blocked", "reason": "Operational database path is not a regular, non-symlink file"}
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
            counts = dict(connection.execute("SELECT status, COUNT(*) FROM event_tracker GROUP BY status"))
            due = connection.execute(
                "SELECT COUNT(*) FROM event_tracker WHERE status='pending' "
                "AND julianday(next_query_time)<=julianday('now')"
            ).fetchone()[0]
    except sqlite3.Error:
        return {"status": "unverified", "reason": "Existing operational database schema could not be inspected read-only"}
    return {
        "status": "blocked" if due else "usable",
        "reason": ("Overdue work will be processed on startup; decide whether to retain this queue before activation"
                   if due else "No overdue pending work in the inspected closed queue"),
        "counts": counts,
        "overdue_pending": due,
    }


def profile_report(deployment, base_url, name):
    """Read static findings from the installed service, never the host profile."""
    report = deployment.get_json(base_url + "/configurations/" + quote(name, safe="") + "/check")
    if (not isinstance(report, dict) or report.get("configuration") != name
            or report.get("scope") != "static"
            or report.get("status") not in {"NO_KNOWN_BLOCKERS", "BLOCKED", "INCOMPLETE"}
            or not isinstance(report.get("findings"), list)
            or not isinstance(report.get("capabilities"), dict)):
        raise ValueError("unsupported configuration-check response")
    # Retain the component's actionable fields, not arbitrary API material. This
    # preserves exact files/keys/paths without dumping environment or private data.
    fields = {"status", "code", "configuration", "config_file", "section", "key", "reference",
              "resolved_path", "reason", "corrective_action", "evidence"}
    return {
        "configuration": name,
        "status": {"NO_KNOWN_BLOCKERS": "usable", "BLOCKED": "blocked", "INCOMPLETE": "unverified"}[report["status"]],
        "scope": "static",
        "native_execution": "not_run",
        "capabilities": {"native_configuration_diagnostics": report.get("capabilities", {}).get("native_configuration_diagnostics") is True},
        "findings": [{key: value for key, value in finding.items() if key in fields}
                     for finding in report["findings"] if isinstance(finding, dict)],
    }


def build_report(deployment, config_path):
    """Collect independent installation facts; never repair or activate them."""
    findings = []
    profiles = {}
    warnings = []

    def add(component, name, status, reason, action, **details):
        findings.append({"component": component, "check": name, "status": status,
                         "reason": reason, "corrective_action": action, **details})

    settings_parsed = True
    try:
        settings = deployment.read_settings(
            config_path,
            warning_handler=warnings.append,
        )
    except deployment.DeploymentError as error:
        settings_parsed = False
        settings = {}
        add(
            "deployment",
            "settings",
            "blocked",
            str(error),
            "Create/review the literal settings file using deployment.env.example",
            config_file=str(config_path),
        )

    # A parser refusal says the settings are unknown, not absent. Keep its
    # actionable migration error without manufacturing a missing-key list from
    # an empty fallback dictionary. Independent Docker and queue reads continue.
    problems = deployment.settings_problems(settings) if settings_parsed else []
    invalid = (
        {key for key, _reason in problems}
        if settings_parsed else
        deployment.KEYS | deployment.OPTIONAL_KEYS
    )

    for key, reason in problems:
        add(
            "deployment",
            "setting",
            "blocked",
            reason,
            "Correct this setting; no value was applied",
            config_file=str(config_path),
            key=key,
        )

    # A failed Docker connection is not proof that either canonical container
    # or image is absent. Settings and service diagnostics still continue.
    caller_running = None
    try:
        names = deployment.run(["docker", "container", "ls", "--all", "--format", "{{.Names}}"],
                               cwd=deployment.ROOT, capture=True).splitlines()
    except deployment.DeploymentError:
        names = None
        add("deployment", "docker", "unverified", "Docker inventory is unavailable",
            "Restore Docker access and rerun make check")
    if names is not None:
        for component, image_name, container_name in (("pyfinder", "pyfinder:dev", "pyfinder-docker"),
                                                      ("shakemap", "shakemap-docker:latest", "shakemap-docker")):
            try:
                image = deployment.inspect("image", image_name)
                add(component, "image", "usable", "Canonical image can be inspected; source freshness is not inferred",
                    "Rebuild deliberately when deploying source changes", image=image_name, image_id=image.get("Id"))
            except deployment.DeploymentError:
                image = None
                add(component, "image", "unverified", "Canonical image could not be inspected",
                    f"Inspect Docker access or run make build COMPONENT={component}", image=image_name)
            if container_name not in names:
                if component == "pyfinder":
                    caller_running = False
                add(component, "container", "blocked", "Canonical container is absent",
                    f"Review prerequisites and queue intent before make start COMPONENT={component}", container=container_name)
                continue
            try:
                container = deployment.inspect("container", container_name)
                running = container.get("State", {}).get("Running") is True
                if component == "pyfinder":
                    caller_running = running
                add(component, "container", "usable" if running else "blocked",
                    "Canonical container is running" if running else "Canonical container is stopped",
                    f"Use make start COMPONENT={component} only after reviewing prerequisites", container=container_name)
                if image is not None and not invalid:
                    wiring = deployment.container_problems(settings, component, image, container)
                    add(component, "wiring", "blocked" if wiring else "usable",
                        "; ".join(wiring) if wiring else "Image, mounts and configured caller environment match",
                        "Reconcile the reported settings without deleting mounted data")
                elif invalid:
                    add(component, "wiring", "unverified", "Incomplete settings prevent a wiring comparison",
                        "Correct the settings and rerun make check")
            except deployment.DeploymentError:
                add(component, "container", "unverified", "Canonical container inspection failed",
                    "Restore Docker access and rerun make check", container=container_name)

    queue_path = deployment.PYFINDER_RUNTIME / "pyfinder/state/scheduled_queries.sqlite3"
    queue = backlog(queue_path, caller_running=caller_running)
    add("pyfinder", "queue", queue.pop("status"), queue.pop("reason"),
        "Preserve the queue; explicitly decide how existing pending work should be handled before activation",
        resolved_path=str(queue_path), **queue)

    catalog = {}
    if not invalid:
        try:
            caller = caller_settings(deployment, settings)
            warnings.extend(caller.get("warnings", []))
            catalog = caller.get("settings", {}).get("regional_configurations", {})
            if caller["status"] == "ready" and (
                not isinstance(catalog, dict) or not catalog
            ):
                raise ValueError("caller routing catalog unavailable")

            # A blocked caller report is authoritative even when validation
            # stopped before it could describe routing. Preserve its corrective
            # finding instead of calling a working checker "unavailable".
            if not isinstance(catalog, dict):
                catalog = {}

            add(
                "pyfinder",
                "source_settings",
                "usable" if caller["status"] == "ready" else "blocked",
                (
                    "PyFinder source settings pass static checks"
                    if caller["status"] == "ready" else
                    "PyFinder settings are incomplete or disabled"
                ),
                "Review the component findings and saved settings",
                scope="source_configuration",
                component_report=caller,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            add("pyfinder", "source_settings", "unverified", "The component settings checker is unavailable",
                "Install the configured PyFinder host dependencies/check interface and rerun make check")
    else:
        add("pyfinder", "source_settings", "unverified", "Invalid deployment settings prevent component validation",
            "Correct the reported settings before checking application configuration")

    email = settings.get("PYFINDER_ALERT_CONFIG")
    add(
        "pyfinder",
        "email_policy",
        "usable" if email == "" else "unverified",
        (
            "Email policy is unknown because deployment settings could not be parsed"
            if not settings_parsed else
            "Email is explicitly disabled"
            if email == "" else
            "Email is configured or uses implicit discovery; delivery was not tested"
        ),
        "Set PYFINDER_ALERT_CONFIG empty to disable, or explicitly configure and separately verify delivery",
        config_file=str(config_path),
        key="PYFINDER_ALERT_CONFIG",
    )

    requested = list(dict.fromkeys(catalog.values()))
    if "SHAKEMAP_PORT" not in invalid:
        base_url = "http://127.0.0.1:" + settings["SHAKEMAP_PORT"]
        try:
            health = deployment.get_json(base_url + "/healthz")
            ready = health.get("ready") if isinstance(health, dict) else None
            status = "usable" if ready is True else "blocked" if ready is False else "unverified"
            reason = ("Service reports ready" if ready is True else "Service reports not ready"
                      if ready is False else "Service returned no supported readiness value")
            add("shakemap", "service_health", status, reason,
                "Inspect service diagnostics; use explicit finalization only when intended")
        except deployment.DeploymentError:
            add("shakemap", "service_health", "unverified", "Service health could not be read",
                "Inspect the service endpoint and canonical container; no service was started")
        for name in dict.fromkeys(["global", *requested]):
            try:
                profiles[name] = profile_report(deployment, base_url, name)
            except (deployment.DeploymentError, ValueError, TypeError):
                profiles[name] = {"configuration": name, "status": "unverified", "scope": "static",
                                  "native_execution": "not_run", "findings": [{
                                      "status": "UNKNOWN", "reason": "Installed service configuration-check endpoint is unavailable or unsupported",
                                      "corrective_action": "Deploy a service with the check endpoint, then rerun make check; no native execution was performed"}]}
    else:
        add("shakemap", "configuration_checks", "unverified", "A valid service port is required for installed checks",
            "Correct SHAKEMAP_PORT; no host-profile substitution was used")

    recovery = {}
    if not catalog:
        add(
            "shakemap",
            "regional_routing",
            "unverified",
            "Caller routing catalog is unavailable",
            "Use compatible PyFinder and deployment versions; no profile was selected",
        )

    # Assess every configured profile separately. Keep a possible global
    # recovery visibly conditional rather than turning static checks green.
    for name in dict.fromkeys(["global", *requested]):
        profile = profiles.get(name, {"status": "unverified"})
        status = profile["status"]
        recovery[name] = "not_needed" if name == "global" else "unverified"
        if name != "global" and status == "blocked":
            global_profile = profiles.get("global", {})
            classification = profile.get("capabilities", {}).get(
                "native_configuration_diagnostics"
            ) is True

            if global_profile.get("status") == "usable" and classification:
                # A usable global static profile is only a possible recovery:
                # the installed caller must still attempt the region first.
                status = "unverified"
                recovery[name] = "conditional_on_installed_caller"
            else:
                status = (
                    "blocked"
                    if global_profile.get("status") == "blocked" else
                    "unverified"
                )

        add(
            "shakemap",
            "routing_configuration",
            status,
            "Static capability for configured routing; no event or native execution was selected",
            "Review profile findings; do not silently skip a regional request",
            configuration=name,
            recovery=recovery[name],
        )

    return {
        "scope": "read_only_static", "status": aggregate([item["status"] for item in findings]),
        "findings": findings,
        "warnings": warnings,
        "configurations": profiles,
        "regional_configurations": catalog,
        "recovery": {
            "profiles": recovery, "requested_configuration_first": True,
            "requires_confirmed_eligible_failure": True,
            "explanation": "PyFinder must submit the requested region first. Only its confirmed eligible failure may lead to a second global request. Global static checks do not prove native success.",
            "installed_caller_behavior": "unverified",
        },
        "limits": ["No native/provider/SMTP execution, container changes, data provisioning or queue changes occurred",
                   "Source settings and static service findings do not prove installed caller behavior or scientific coverage",
                   "Every configured routing profile and global contributes to this static assessment"],
    }


def format_report(report):
    """Keep routine operator output readable; structured details remain opt-in."""
    findings = report.get("findings", [])
    lines = [f"Deployment check: {report['status'].upper()} (read-only static checks)"]

    # Warnings describe settings that had no effect. They do not participate
    # in readiness aggregation or hide errors in the supported configuration.
    if report.get("warnings"):
        lines.append("\nWarnings (obsolete settings ignored):")
        for warning in report["warnings"]:
            lines.append("- " + warning)

    # Show the reason and next action together. Component validation can explain
    # a failure more precisely than the deployment-level summary.
    issues = [item for item in findings if item["status"] != "usable"
              and item["check"] != "routing_configuration"]
    lines.append("\nRequired issues and actions:" if issues else "\nNo required static issues reported.")
    for item in issues:
        label = f"{item['component']} {item['check'].replace('_', ' ')}"
        lines.append(f"- {item['status'].upper()} — {label}: {item['reason']}")
        for detail in item.get("component_report", {}).get("checks", []):
            if detail.get("reason"):
                lines.append(f"  {detail['reason']}")
        location = [str(item[key]) for key in ("config_file", "key", "resolved_path") if item.get(key)]
        if location:
            lines.append("  Location: " + " | ".join(location))
        if "overdue_pending" in item:
            lines.append(f"  Overdue pending: {item['overdue_pending']}; queue counts: "
                         + ", ".join(f"{name}={count}" for name, count in sorted(item["counts"].items())))
        lines.append(f"  Action: {item['corrective_action']}")

    passed = [f"{item['component']} {item['check'].replace('_', ' ')}" for item in findings
              if item["status"] == "usable" and item["check"] != "routing_configuration"]
    if passed:
        lines.append("\nStatic checks passed: " + "; ".join(passed) + ".")

    profiles = report.get("configurations", {})
    catalog = report.get("regional_configurations", {})
    lines.append("\nRegional routing: " + (", ".join(f"{country} -> {name}" for country, name in sorted(catalog.items())) or "unverified"))
    lines.append("Configurations (per-profile static capability):")
    lines.append("  " + "; ".join(f"{name}: {profile['status'].upper()}"
                                  for name, profile in profiles.items()) if profiles
                 else "  No installed configuration diagnostics available.")

    # The same missing endpoint can affect every profile. Group identical
    # findings once while preserving all affected names and their statuses.
    groups = []
    for name, profile in profiles.items():
        details = [finding for finding in profile.get("findings", []) if finding.get("status") != "OK"]
        for names, existing in groups:
            if details == existing:
                names.append(name)
                break
        else:
            groups.append(([name], details))
    for names, details in groups:
        for detail in details:
            lines.append(f"- {', '.join(names)}: {detail.get('reason', 'Static finding requires review')}")
            for key, label in (("config_file", "File"), ("section", "Section"), ("key", "Key"),
                               ("reference", "Reference"), ("resolved_path", "Resolved path")):
                if detail.get(key):
                    value = detail[key]
                    if isinstance(value, list):
                        value = " / ".join(str(part) for part in value)
                    lines.append(f"  {label}: {value}")
            if detail.get("corrective_action"):
                lines.append(f"  Action: {detail['corrective_action']}")

    recovery = report.get("recovery", {})
    lines.append("\nFallback: " + recovery.get("explanation", "Recovery has not been assessed."))
    lines.append("  Installed caller recovery is unverified; global native success is not assured.")
    lines.append("\nLimits: no native/provider/SMTP execution or runtime changes. Static checks do not prove")
    lines.append("installed source freshness, scientific coverage or native success. Every configured routing")
    lines.append("profile and global contributes to this assessment. Use --json for full details.")
    return "\n".join(lines)


def check(deployment, config_path, *, json_output=False):
    """Print the operator report; reserve success for known usable capabilities."""
    report = build_report(deployment, config_path)
    print(json.dumps(report, indent=2, sort_keys=True) if json_output else format_report(report))
    return {"usable": 0, "degraded": 0, "blocked": 1, "unverified": 2}[report["status"]]
