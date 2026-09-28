"""Explicit synthetic ShakeMap fixture verification using installed PyFinder.

This module contains verification logic only. Its source travels on stdin with
our finite container probe; application classes must come from the built image.
"""

from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import time


REGIONAL_FILES = ("gmpe_sets.conf", "model.conf", "modules.conf", "products.conf", "select.conf")


def validate_fixture(fixture, event_id):
    """Keep synthetic units, physical origin and caller identity explicit."""
    keys = {"synthetic", "configuration", "origin_time", "latitude", "longitude",
            "depth_km", "magnitude", "stations"}
    if not isinstance(fixture, dict) or set(fixture) != keys or fixture["synthetic"] is not True:
        raise ValueError("Fixture must contain exactly the documented synthetic fields")
    if not isinstance(event_id, str) or not re.fullmatch(r"pyfinder-verification-[A-Za-z0-9_-]+_t00000", event_id):
        raise ValueError("Use an explicit fresh pyfinder-verification-..._t00000 ID")
    if len(event_id) > 231:
        raise ValueError("Fixture calculation ID exceeds the service limit")
    if not isinstance(fixture["configuration"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", fixture["configuration"]):
        raise ValueError("Fixture configuration must be an explicit service name")
    try:
        origin = datetime.fromisoformat(fixture["origin_time"].replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Fixture origin_time must be an explicit physical UTC timestamp") from None
    if origin.tzinfo is None or origin.utcoffset().total_seconds() != 0:
        raise ValueError("Fixture origin_time must identify UTC explicitly")

    def number(value, label, minimum, maximum):
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"Fixture {label} is outside its finite physical range")

    for key, minimum, maximum in (("latitude", -90, 90), ("longitude", -180, 180),
                                  ("depth_km", 0, 700), ("magnitude", 0, 10)):
        number(fixture[key], key, minimum, maximum)
    stations = fixture["stations"]
    station_keys = {"network", "station", "location", "channel", "latitude", "longitude", "pga_cm_s2"}
    if not isinstance(stations, list) or not stations:
        raise ValueError("Fixture must provide synthetic station PGA in cm/s²")
    identities = set()
    for station in stations:
        if not isinstance(station, dict) or set(station) != station_keys:
            raise ValueError("Fixture station fields differ from the documented schema")
        for key in ("network", "station", "location", "channel"):
            value = station[key]
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]*", value) or (not value and key != "location"):
                raise ValueError("Fixture station identity must be explicit SNCL components")
        identity = tuple(station[key] for key in ("network", "station", "location", "channel"))
        if identity in identities:
            raise ValueError("Fixture repeats a component identity")
        identities.add(identity)
        number(station["latitude"], "station latitude", -90, 90)
        number(station["longitude"], "station longitude", -180, 180)
        number(station["pga_cm_s2"], "station PGA cm/s²", 0, 1e6)
        if station["pga_cm_s2"] == 0:
            raise ValueError("Fixture station PGA must be positive")
    return fixture


def mapped_service_path(advertised, host_service, local_service):
    """Map only exact advertised host-service paths into the existing bind."""
    if not isinstance(advertised, (str, Path)):
        raise ValueError("Service evidence path is not published yet")
    advertised = Path(advertised)
    if not advertised.is_absolute() or ".." in advertised.parts:
        raise ValueError("Service evidence path is not an absolute contained path")
    relative = advertised.relative_to(host_service)
    mapped = local_service / relative
    if mapped.resolve(strict=True) != mapped:
        raise ValueError("Service evidence path uses a symlink")
    return mapped


def file_identity(path):
    """Hash actual retained bytes with bounded memory."""
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("Evidence file is missing, redirected or not regular")
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"size": path.stat().st_size, "sha256": digest.hexdigest()}


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def prepare_fixture(fixture, event_id):
    """Use installed manager preparation without acquisition or FinDer execution."""
    from pyfinder.eventcontext import EventContext
    from pyfinder.findermanager import FinDerManager
    from pyfinder.finderutils import FinderChannel, FinderChannelList, FinderEvent, FinderSolution

    manager = object.__new__(FinDerManager)
    manager.entry_kind = FinDerManager.ALERT_BACKED
    manager.metadata = {"current_delay": 0}
    manager.event_context = EventContext(
        event_id.removesuffix("_t00000"), fixture["latitude"], fixture["longitude"],
        fixture["magnitude"], fixture["depth_km"], fixture["origin_time"],
    )
    physical_time = datetime.fromisoformat(fixture["origin_time"].replace("Z", "+00:00"))
    solution = FinderSolution(
        event_id=manager.event_context.get_event_id(), finder_event_id="synthetic-fixture",
        event=FinderEvent(latitude=fixture["latitude"], longitude=fixture["longitude"],
                          depth=fixture["depth_km"], magnitude=fixture["magnitude"],
                          origin_time_epoch=physical_time.timestamp()),
        rupture=None,
        channels=FinderChannelList([
            FinderChannel(latitude=station["latitude"], longitude=station["longitude"],
                          network_code=station["network"], station_code=station["station"],
                          location_code=station["location"], channel_code=station["channel"],
                          pga=station["pga_cm_s2"], is_artificial=False)
            for station in fixture["stations"]
        ]),
    )
    prepared_id, files = manager.prepare_shakemap(solution)
    if prepared_id != event_id or set(files) != {"event.xml", "event_dat.xml"}:
        raise ValueError("Installed exporter changed fixture identity or point input shape")
    return files


def verify_terminal(record, files, fixture, workspace, host_service, local_service, client):
    """Retain failure logs first, then validate exact terminal evidence."""
    from pyfinder.services.shakemap_client import AcceptedJob

    details = record["observation"]["details"]
    sequence = record["internal_sequence"]
    # poll() validates the event envelope and returns its selected job row.
    # That row has a sequence, not an event_id; the durable request owns the ID.
    event_id = record["request"]["event_id"]
    acknowledgement = record["acknowledgement"]
    if (acknowledgement["event_id"] != event_id
            or acknowledgement["internal_sequence"] != sequence
            or details["internal_sequence"] != sequence):
        raise ValueError("Terminal evidence differs from the accepted calculation identity")
    if record["request"]["configuration"] != fixture["configuration"]:
        raise ValueError("Durable request differs from the explicit fixture configuration")
    paths = details["shared_paths"]
    if details["job_completed"] is not True:
        raise ValueError("Terminal status lacks a completed native job")
    if details["status"] == "FAILED" and details["products_ready"] is not False:
        raise ValueError("Failed native job incorrectly advertises ready products")
    mapping = lambda value: mapped_service_path(value, host_service, local_service)
    copied = {}
    for label in ("service_log", "shake_log", "provenance", "product_manifest"):
        try:
            source = mapping(paths[label])
            if not source.is_file():
                raise ValueError("evidence is not a regular file")
            destination = workspace / (label + (".json" if label in {"provenance", "product_manifest"} else ".log"))
            destination.write_bytes(source.read_bytes())
            copied[label] = str(destination)
        except (OSError, ValueError, KeyError) as error:
            copied[label] = {"unavailable": type(error).__name__}
    save_json(workspace / "evidence-availability.json", copied)

    provenance = json.loads((workspace / "provenance.json").read_text())
    if provenance["event_id"] != event_id or provenance["internal_sequence"] != sequence:
        raise ValueError("Provenance belongs to another calculation")
    selected = fixture["configuration"]
    materialized = provenance["configuration"]["materialization"]
    if provenance["request"]["configuration"] != selected or provenance["configuration"]["selected"] != selected:
        raise ValueError("Service changed the caller-selected configuration")
    if materialized["selected_configuration"] != selected:
        raise ValueError("Native profile selection differs from the request")

    event_service = local_service / ".service/events" / event_id
    snapshot = event_service / "request"
    if set(path.name for path in snapshot.iterdir()) != set(files):
        raise ValueError("Retained native request contains missing or stale files")
    for name, contents in files.items():
        if (snapshot / name).read_bytes() != contents:
            raise ValueError("Retained native request bytes differ from exported inputs")

    profile = event_service / "profile"
    identities = {}
    for item in provenance["configuration"]["profile_files"]:
        if item["identity"] is None:
            continue
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe profile inventory path")
        actual = file_identity(profile / relative)
        if actual != item["identity"]:
            raise ValueError("Selected profile bytes differ from recorded identity")
        identities[str(relative)] = actual
    if materialized["materialized"] is True:
        if not {"install/config/" + name for name in REGIONAL_FILES} <= identities.keys():
            raise ValueError("Materialized profile lacks required configuration identities")
    if materialized["materialized"] is True and selected != "global":
        source = local_service / "data/regional" / selected
        expected_source = str(local_service / "data/regional" / selected)
        if materialized["source_directory"] != expected_source:
            raise ValueError("Regional materialization used another source directory")
        for name in REGIONAL_FILES:
            if file_identity(source / name) != file_identity(profile / "install/config" / name):
                raise ValueError("Regional native profile differs from selected source")

    # Profile byte identities prove what was selected. Record data references
    # separately: a manifest declaration alone is not evidence of native use.
    references = {}
    for filename, setting in (("model.conf", "vs30file"), ("products.conf", "topography")):
        configuration_file = profile / "install/config" / filename
        if configuration_file.is_file():
            matches = re.findall(r"^\s*" + setting + r"\s*=\s*([^#\r\n]+)", configuration_file.read_text(), re.MULTILINE)
            references[setting] = [value.strip() for value in matches]
    save_json(workspace / "profile-evidence.json", {
        "selected_configuration": selected, "profile_identities": identities,
        "data_references": references, "large_dataset_declarations": provenance["large_datasets"],
        "native_dataset_use": "not_independently_observed",
    })

    if details["status"] == "SUCCESS":
        if details["products_ready"] is not True or materialized["materialized"] is not True:
            raise ValueError("Native SUCCESS lacks ready products or selected materialization")
        manifest = json.loads((workspace / "product_manifest.json").read_text())
        if manifest["event_id"] != event_id or manifest["internal_sequence"] != sequence:
            raise ValueError("Manifest belongs to another calculation")
        required = manifest["required_products"]
        if manifest["partial"] is not False or manifest["inventory_failures"] or required["passed"] is not True:
            raise ValueError("Product manifest is partial or its core-product gate failed")
        if not required["checks"] or not all(check["passed"] is True for check in required["checks"]):
            raise ValueError("Core-product checks are missing or failed")
        product_root = mapping(paths["products"])
        inventory = {item["path"]: item for item in manifest["products"]}
        if not {"shake_result.hdf", "grid.xml", "intensity.jpg"} <= inventory.keys():
            raise ValueError("Core ShakeMap products are absent")
        if not set(required["paths"]) <= inventory.keys():
            raise ValueError("Core products are missing from inventory")
        for relative, item in inventory.items():
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe product inventory path")
            if file_identity(product_root / path) != {"size": item["size"], "sha256": item["sha256"]}:
                raise ValueError("Product bytes differ from manifest")
        for name in ("service_log", "shake_log"):
            if not (workspace / (name + ".log")).read_bytes():
                raise ValueError("Required native/service log is empty")
        save_json(workspace / "products-api.json", client.current_products(AcceptedJob(event_id, sequence)))
        if selected == "global":
            for setting, name, relative in (
                ("vs30file", "vs30", "global/vs30/global_vs30.grd"),
                ("topography", "topography", "global/topo/topo_30sec.grd"),
            ):
                asset = local_service / "data" / relative
                if references.get(setting) != [str(asset)]:
                    raise ValueError("Global native profile did not select its managed grid")
                declaration = provenance["large_datasets"]["global"][name]["manifest_identity"]
                if file_identity(asset) != {"size": declaration["size"], "sha256": declaration["sha256"]}:
                    raise ValueError("Selected global grid differs from managed identity")
    return {"outcome": details["status"], "internal_sequence": sequence,
            "selected_configuration": selected, "profile_identity_count": len(identities),
            "native_dataset_use": "not_independently_observed", "deployment_ready": False}


def run_calculation(context, client, *, clock=time.monotonic, sleeper=time.sleep,
                    local_service=Path("/home/sysop/runtime/shakemap")):
    """Submit once, persist locally, and observe only the accepted sequence."""
    from pyfinder.services.shakemap_inputs import PreparedShakeMapInputs
    from pyfinder.services.shakemap_workflow import ShakeMapWorkflow

    fixture = validate_fixture(context["calculation_fixture"], context["event_id"])
    event_id = context["event_id"]
    host_service = Path(context["host_service"])
    workspace = Path(context["calculation_workspace"])
    workflow = None
    record = None
    workspace_created = False
    result = {"classification": "HARNESS_FAILED", "outcome": None,
              "workspace": str(workspace), "event_id": event_id, "deployment_ready": False}
    try:
        if Path(client.configuration()["shared_service_root"]) != host_service:
            raise ValueError("Service advertises another underlying runtime")
        if fixture["configuration"] not in client.configurations()["configurations"]:
            raise ValueError("Explicit fixture configuration is unavailable")
        capacity = client.queue()["capacity"]
        if capacity["running"] != 0 or capacity["queued"] != 0:
            raise ValueError("Service queue is not idle before the controlled fixture")
        for branch in ("data/inputs", "products", ".service/events"):
            path = local_service / branch / event_id
            if path.exists() or path.is_symlink():
                raise ValueError("Fixture ID already owns service files")
        if list((local_service / ".service/archive").glob(event_id + "-*")):
            raise ValueError("Fixture ID already owns an archive")
        if any(row["event_id"] == event_id for row in client.events()["jobs"]):
            raise ValueError("Fixture ID is already visible through the service")
        # The parent calculation workspace is reserved atomically; never adopt
        # earlier playback or scientific work merely because a child is absent.
        workspace.parent.mkdir(exist_ok=False)
        workspace.mkdir()
        workspace_created = True
        save_json(workspace / "fixture.json", fixture)
        files = prepare_fixture(fixture, event_id)
        inputs = workspace / "native-inputs"
        inputs.mkdir()
        for name, contents in files.items():
            (inputs / name).write_bytes(contents)
        workflow = ShakeMapWorkflow(workspace / "workflow.sqlite", client)
        with PreparedShakeMapInputs(local_service / "data/inputs").submission(event_id, files):
            record = workflow.submit("fixture", event_id, files,
                                     configuration=fixture["configuration"], overwrite=True)
        save_json(workspace / "accepted.json", record)
        sequence = record["internal_sequence"]
        deadline = clock() + 600
        while clock() < deadline:
            record = workflow.poll("fixture")
            save_json(workspace / "observed.json", record)
            if record["internal_sequence"] != sequence:
                raise ValueError("Observed sequence changed after acceptance")
            outcome = record["observation"]["details"]["status"]
            if outcome in {"SUCCESS", "FAILED"}:
                # Native execution and evidence validation are separate facts.
                # Keep the observed outcome even if a later evidence check fails.
                result.update(outcome=outcome, internal_sequence=sequence)
                result.update(verify_terminal(record, files, fixture, workspace, host_service, local_service, client))
                result["classification"] = "NATIVE_TERMINAL"
                break
            sleeper(2)
        else:
            result["classification"] = "TIMEOUT"
    except Exception as error:
        if workflow is not None:
            try:
                record = workflow.get("fixture")
                if record is not None:
                    save_json(workspace / "last-record.json", record)
                    if record["submission_state"] in {"SUBMITTING", "UNCERTAIN"}:
                        result["classification"] = "SUBMISSION_UNCERTAIN"
            except Exception as evidence_error:
                result["record_error"] = type(evidence_error).__name__
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if workflow is not None:
            workflow.close()
        if workspace_created:
            # Preserve diagnostic paths even when a bounded run stops before a
            # terminal product manifest exists. Do not modify a collided workspace.
            if record is not None and record.get("observation"):
                details = record["observation"].get("details", {})
                for label in ("service_log", "shake_log"):
                    try:
                        source = mapped_service_path(details["shared_paths"][label], host_service, local_service)
                        (workspace / (label + ".log")).write_bytes(source.read_bytes())
                    except (OSError, ValueError, KeyError):
                        pass
            save_json(workspace / "calculation-summary.json", result)
    return result
