# Installation and operations

Follow the [README installation sequence](../README.md) for the normal path.
This guide supplies prerequisites, configuration details and recovery procedures.
Commands run from `pyfinder-deploy` unless stated otherwise.

## Host prerequisites

Provide Docker with a working daemon, Bash, Make, Git and Python 3.11 or newer.
Host Python runs the container-management tools and the `shake-in-docker` command,
which sends HTTP requests to ShakeMap. The earthquake calculations and their
application dependencies run inside Docker. The host Python version need not
match the containers; ordinary deployment needs no host PyFinder or ParamWS install.

Choose a writable host workspace of your own and use this supported sibling
layout. The finite caller verifier requires `.venv` at the workspace root.
The workspace itself need not have a particular name or live under a particular
user's home directory:

```text
workspace/
├── .venv/
├── pyfinder/
├── shakemap-docker/
└── pyfinder-deploy/
    ├── deployment.env
    └── runtime/
        ├── pyfinder/
        └── shakemap/
```

For a new installation, change the workspace example to your chosen location and
clone the three repositories there. For existing checkouts, use their common
parent and skip clones already present. `cd -P` selects the physical path, so an
environment created through a symlink does not acquire a different path identity.

```sh
PYFINDER_WORKSPACE="$HOME/pyfinder-workspace"
mkdir -p "$PYFINDER_WORKSPACE"
cd -P "$PYFINDER_WORKSPACE"
git clone https://github.com/pyfinder-dev/pyfinder.git
git clone https://github.com/pyfinder-dev/shakemap-docker.git
git clone https://github.com/pyfinder-dev/pyfinder-deploy.git
```

Create the environment once, from that workspace. If `.venv` already exists,
activate and check it instead of rerunning the creation command. An incompatible
or broken existing environment needs a deliberate operator decision; these helpers
do not replace it.

```sh
# Run only when this workspace has no .venv yet.
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "Use Python 3.11 or newer for host helpers")'
python3 -m venv .venv
```

If `python3` is too old, use your installed Python 3.11+ command for both commands
above. Activate the environment, confirm that `python` resolves inside it and
reports Python 3.11 or newer, then enter the deployment checkout:

```sh
source .venv/bin/activate
command -v python
python --version
cd pyfinder-deploy
```

Install those host tools from the local ShakeMap checkout into this environment.
This creates the `shake-in-docker` command; it does not install the USGS ShakeMap
calculation software on the host. Stop and correct any installation error:

```sh
python -m pip install -e ../shakemap-docker
```

The current shared package also installs its declared service libraries
(`configobj`, FastAPI, multipart and Uvicorn). The build and lifecycle helpers
require the installed host command. The caller settings check can read the
PyFinder source checkout without installing its scientific dependencies.
Use `../pyfinder/scripts/pyfinder` to run workflows in the application container.
Optional host application tests and comprehensive `make verify-native` have
[separate test prerequisites](verification.md#optional-developer-host-tests).

Activation applies only to the current shell. In each new terminal, replace this
placeholder with your own workspace path, return to the deployment checkout and
reactivate before running helpers:

```sh
cd -P "/absolute/path/to/your/workspace/pyfinder-deploy"
source ../.venv/bin/activate
command -v python
```

Do not recreate the environment or reinstall dependencies merely to open another
terminal. Helpers validate prerequisites but do not create the environment,
clone repositories or install packages for you.

Canonical images are `pyfinder:dev` and `shakemap-docker:latest`; containers are
`pyfinder-docker` and `shakemap-docker`. FinDer comes from the required
`ghcr.io/sceylan/finder-base:gmt5` base image. The legacy `pyfinder-docker` repository
is not part of this installation. Builds and data provisioning need upstream
access; resolve TLS/checksum errors rather than bypassing validation.

## Settings and connectivity

`make setup` copies [deployment.env.example](../deployment.env.example) only when
the selected file is absent and creates missing caller runtime directories.
It preserves existing files and does not recursively change ownership. Print
the three required resolved paths before editing `deployment.env`:

```sh
(cd ../pyfinder && pwd -P)
(cd ../shakemap-docker && pwd -P)
(cd runtime && pwd -P)
```

Use these for `PYFINDER_REPOSITORY`, `SHAKEMAP_REPOSITORY` and
`SHAKEMAP_RUNTIME_ROOT`, respectively. Runtime must be this deployment checkout's
`runtime` directory. Operational helpers accept alternate literal settings files
via `--config /absolute/path/to/deployment.env`; these do not select another runtime.

Settings are literal `KEY=value` lines. Do not use quotes, `export`, inline comments,
`~`, `$HOME`, `$PWD` or shell substitutions. Paths may contain spaces. Unknown,
duplicate, missing or malformed supported settings are rejected. The obsolete
`PYFINDER_SHAKEMAP_CONFIGURATION` key warns and is ignored in settings or the
environment; its value is neither applied nor displayed. Removal is recommended,
not required for activation. Profile selection belongs to PyFinder's catalog.

The shell's `PYFINDER_WORKSPACE` variable and `$HOME` above are conveniences for
terminal setup; they are not expanded inside `deployment.env`. Copy your resolved
host paths into that file. Paths under `/home/sysop/runtime` are fixed paths inside
the containers, not host paths to replace with your workspace location.

### Choose the ShakeMap URL

`PYFINDER_SHAKEMAP_URL` is used **inside the PyFinder container**. ShakeMap's helper
publishes container port `9010` on the Docker host at `SHAKEMAP_PORT` from
`deployment.env` (default `9010`). The URL therefore combines a host address that
PyFinder can reach with that published host port. If you choose
`SHAKEMAP_PORT=19010`, the URL must end in `:19010`, even though ShakeMap's internal
port remains `9010`.

Choose the address for your installation:

| Docker installation | Address to use |
| --- | --- |
| Docker Desktop | `host.docker.internal`, the documented alias for the host |
| Docker Engine on Linux with a regular root-managed daemon and the default IPv4 bridge | The host bridge gateway reported by the read-only command below |
| Custom/rootless networking or a remote Docker daemon | An address reachable from that container network on the daemon host; the two shortcuts above are not universal |

For Docker Desktop with the default published port, save these literal lines:

```text
SHAKEMAP_PORT=9010
PYFINDER_SHAKEMAP_URL=http://host.docker.internal:9010
```

Docker documents the Desktop alias in
[container-to-host networking](https://docs.docker.com/desktop/features/networking/networking-how-tos/#connect-a-container-to-a-service-on-the-host).

For that regular Linux Docker Engine setup, inspect the default bridge:

```sh
docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'
```

For the standard IPv4 bridge this prints the host gateway address. If the actual
output is `172.17.0.1`, the default-port example becomes:

```text
SHAKEMAP_PORT=9010
PYFINDER_SHAKEMAP_URL=http://172.17.0.1:9010
```

Copy your own returned IPv4 address; `172.17.0.1` is only an example. If the
command returns no address, an IPv6 address or an unexpected network, do not guess
from this example. Check the network configuration with whoever manages that
Docker daemon. A custom port binding, firewall or rootless/custom network can
require a different reachable host address. See Docker's
[network inspection reference](https://docs.docker.com/reference/cli/docker/network/inspect/),
[bridge networking](https://docs.docker.com/engine/network/drivers/bridge/) and
[published-port behavior](https://docs.docker.com/engine/network/port-publishing/).

The current PyFinder launcher and its one-time connection check use Docker's
default bridge. They do not create a shared named network, add automatic
container-name resolution or add a `host.docker.internal` host-gateway mapping
on Linux. Do not assume `http://shakemap-docker:9010` will resolve. Inside PyFinder,
`localhost` and `127.0.0.1` refer to PyFinder itself. Host-side `shake-in-docker`
commands can use `http://127.0.0.1:<published-port>` because they run on the host.

After building the images and successfully finalizing ShakeMap, confirm the
saved URL from the PyFinder image using the existing connection check. Keep
`PYFINDER_SHAKEMAP_ENABLED=false` and the canonical `pyfinder-docker` container
absent. Choose a fresh absolute evidence directory outside runtime, whose parent
exists:

```sh
make verify-caller EVIDENCE=/absolute/fresh/evidence-directory
```

Success prints `Finite installed caller checks passed` and writes
`"passed": true` in that directory's `summary.json`. A successful browser or
`curl` request on the host does not establish this container access. On failure,
read the terminal error and any saved summary/process logs, correct the URL,
port or reported service/network/access problem, then repeat with a new evidence directory.
Do not start live PyFinder just to test the address. See the
[connection-check details](verification.md#finite-caller-to-service-probe) for
preconditions and evidence. Keep integration disabled until all checks and
queue/email review are complete.

### Overwrite and email settings

`PYFINDER_SHAKEMAP_OVERWRITE=true` replaces both preceding service and product trees
when a public calculation ID is reused; `false` archives both before recalculation.
Neither setting updates a result file by file.

`PYFINDER_ALERT_CONFIG=` explicitly disables email and is supported in production.
A nonempty value names an existing separate email configuration by its container
path under `/home/sysop/runtime/pyfinder`; the mapped file must not use symlinks.
Omitting the key preserves legacy discovery. Keep credentials and recipients in
that separate file. See [notification configuration](../../pyfinder/README.md);
configured delivery needs explicit verification, not an automatic test mail.

## Data, initialization and ownership

Both containers bind this checkout's `runtime` parent to `/home/sysop/runtime`.
PyFinder prepares inputs at `/home/sysop/runtime/shakemap/data/inputs`; there is
no additional input bind. UID/GID `1000:1000` needs actual writable-path access.
PyFinder owns state, logs, runs and playbacks under `runtime/pyfinder`; ShakeMap
owns `runtime/shakemap`. The shared parent exposes both trees to both containers;
application ownership does not isolate them at the filesystem level. Service
global, regional and test data overlays are read-only; this does not make the
caller's view read-only or authorize changes to scientific datasets.

ShakeMap needs two default datasets to finish installation: a VS30 grid describing
ground conditions and a topography grid used to draw maps. The data helper
downloads the project's recorded versions or imports copies you provide. In this
deployment checkout they are stored at:

- `runtime/shakemap/data/global/vs30/global_vs30.grd`
- `runtime/shakemap/data/global/topo/topo_30sec.grd`

These files support the global configuration used by the installation test and
calculations outside your coverage areas. Your regional files are separate.
Run the helper through `make data COMPONENT=shakemap DATA_ACTION=...`:

| `DATA_ACTION` | Effect |
| --- | --- |
| `inspect` | Show the paths, whether the two files exist and whether they can be read. It does not download files or check all their contents. Missing files are normal on a new installation. |
| `provision` | Download missing files or reuse valid existing copies. Stop and follow the correction if an existing copy is invalid or unreadable; it is left unchanged. |
| `validate` | Read the complete files and compare their checksums with the recorded versions. Continue when `pinned_integrity_valid` is `true`; otherwise follow `corrective_action`. |
| `stage` | Check replacement files without replacing the active copies. Later finalization can activate them when accepted calculations have finished. |

For offline files, run the existing service helper from the **service checkout**.
Replace each path with your own resolved path; `--runtime` must point to this
deployment's `runtime`, not the service checkout's separate default:

```sh
./scripts/manage-shakemap-data.sh provision \
  --runtime /absolute/path/to/pyfinder-deploy/runtime \
  --vs30-source /absolute/path/to/global_vs30.grd \
  --topo-source /absolute/path/to/topo_30sec.grd \
  --no-download
```

The helper verifies the supplied files and installs only missing valid datasets.
If the destination already contains an invalid file, preserve it and follow the
reported replacement instructions; `provision` will not overwrite it. See the
[data reference](../../shakemap-docker/docs/configuration.md#scientific-ownership-and-provisioning)
for staging replacements and additional assets. Direct lifecycle helpers use
`--runtime-root` for the same runtime parent.

`make finalize COMPONENT=shakemap` creates the required directories, checks that
the container can access them and runs the supplied global test earthquake using
the USGS ShakeMap software inside Docker. It may replace the service container
while preserving mounted data. Success leaves ShakeMap running and accepting
calculations. Failure can leave it stopped or unavailable; follow the
reported phase/action and exact [permission recovery instructions](../../shakemap-docker/docs/permissions.md)
when needed; do not elevate the entire finalizer or delete runtime data to fix
access. Ordinary startup does not migrate data or replace incompatible containers.
For a stopped compatible deployment, use `make start COMPONENT=shakemap`.

## Regional configuration

There are two separate choices: which FinDer configuration calculates a solution,
and which ShakeMap configuration uses that result. You can keep the supplied
settings if they fit your workflow. Change coverage or scientific settings only
when your installation needs different ones.

### Configure FinDer profiles

Before building the PyFinder image, review
`../pyfinder/pyfinder/finderconfigs/profiles.py` from the deployment checkout:

1. `GLOBAL_PROFILE` supplies the required global FinDer configuration. Keep it.
2. `REGIONAL_PROFILES` lists the regions you want FinDer to use. Each
   `FinderConfigProfile` has a `name`, a complete `configuration` dictionary and
   a `wkt_filename`. Review the dictionaries imported from `globalconfig.py`,
   `italy.py` and `switzerland.py` in that same directory. Keep, remove or edit
   registered entries as appropriate; a region's name does not determine its data.
3. To add your own configuration, define a complete dictionary in that package,
   import it into `profiles.py` and register it using an existing entry as a
   pattern. Its keys must match the global configuration; omitted values are not
   filled from global. Keep `DATA_FOLDER`: PyFinder replaces that value with the
   calculation's working directory when it writes `finder_file.config`.
4. Put each registered boundary file in
   `../pyfinder/pyfinder/extern/finder_regional_wkt/`. Use valid WGS84
   longitude/latitude `POLYGON` or `MULTIPOLYGON` text. Entries are checked in tuple
   order; the first area covering the location wins, including its boundary.
   Only register files you provide. A broken registered boundary makes FinDer use
   its global configuration with a diagnostic; an uncovered location also uses global.
5. Check that template directories, template IDs and other file paths in your
   dictionaries exist inside the FinDer image or its shared runtime. Host paths
   are not automatically available in the container. The image's FinDer software
   must still come from `ghcr.io/sceylan/finder-base:gmt5`.

These are source files packaged in PyFinder's image. After changes, run
`make build COMPONENT=pyfinder` and follow the caller checks/replacement steps in
the README. `make verify-image` checks installed packages and registered WKT file
presence; it does not establish that your boundaries or scientific settings are
right for your workflow. During a representative [playback](#real-playback), look
for `Selected FinDer configuration:` in its log and review the written
`finder_file.config`. There is no separate generic FinDer-profile check command.

### Choose ShakeMap coverage and native files

PyFinder's `shakemap.regional-configurations` maps your region labels to boundary
files and service profile names. Regions may cross borders, split an area or share
a profile; they need not match the FinDer entries. Selection uses the selected
FinDer solution's location, also written to `event.xml`. Follow the
[README example](../README.md#3-choose-the-configurations-for-your-regions) for
the editable mapping and paths, and
[coverage authoring/provenance](../../pyfinder/docs/shakemap-region-coverage.md).

Uncovered locations use global. Overlaps selecting the same profile select it
once, including borders; conflicting profiles warn and use global. A missing or
unusable optional WKT logs the affected resource and uses global for that calculation
without terminating services. WKT changes require caller rebuild/recreation;
they are separate from service-owned native scientific assets.

Native regional files can be supplied later. Missing optional regional assets
are not global installation/startup prerequisites. The global helper does not
install every regional grid or scientific module. Use the
[per-profile file checklist](../../shakemap-docker/docs/configuration.md#regional-profile-file-checklist)
for all seeded profiles' required grids, original native polygons, models and
host/container paths. Then inspect
the service's exact reported paths and verify the intended profile separately.
A listed name does not establish valid files, scientific coverage or execution.

The service executes the explicit profile and never substitutes another. PyFinder
first attempts the selected region, then may submit global once after a confirmed
configuration failure that permits recovery. It retains the same public ID, original overwrite
policy and both attempts' evidence. Uncertain acceptance, read failures and unrelated
native failures do not authorize recovery. See the
[adapter recovery details](../../pyfinder/docs/shakemap-adapter.md#manager-and-scheduler-integration). Missing regional files
should produce a precise calculation failure while the service remains usable;
static global checks alone do not guarantee successful recovery.

### Install additional ShakeMap models

Skip this step if your profile uses models already available in the ShakeMap
image. `modules.conf` pairs scientific model classes with Python import paths;
the profile check reports imports it cannot find.

If you need another model, its compatible implementation must be installed in
the **ShakeMap image**. Installing it with host `pip` or putting a `.py` beside
`model.conf` does not make it available there. This repository has no universal
custom-model installer: the image maintainer must add the chosen package or
reviewed implementation to the build step in
[the ShakeMap Dockerfile](../../shakemap-docker/Dockerfile). That build stage uses
`/opt/shakemap-env`; the final stage copies that environment. Keep the added model
compatible with the native release and its existing dependencies, and ensure the
class/module pair in `modules.conf` matches the installed code.

Then run `make build COMPONENT=shakemap` followed by
`make finalize COMPONENT=shakemap` from the deployment checkout. Repeat the
profile check and a representative calculation before using the model for live
results. No generic installation command here can choose a model's scientific
implementation or establish its compatibility.

## Upgrade the caller

Update PyFinder and this deployment checkout together. Review the regional catalog
and retain endpoint, input, timeout, enablement, overwrite and email decisions.
The obsolete fixed selector only warns and is ignored; removal is optional.

Stop the caller, inspect container-only changes and preserve anything needed before
removal. Mounted runtime stays in place:

```sh
make stop COMPONENT=pyfinder
docker diff pyfinder-docker
# After preserving necessary container-only files, remove only the stopped container.
docker rm pyfinder-docker
```

Choose one build route. For an ordinary application rebuild:

```sh
make build COMPONENT=pyfinder
```

For an upstream dependency refresh, first confirm the required fix exists upstream,
then use the following command instead. The Dockerfile fetches official ParamWS
`master` and records its commit, but an ordinary build may reuse that cached layer.
Bypass it deliberately for the sibling layout shown above:

```sh
docker build --no-cache --platform linux/amd64 --tag pyfinder:dev ../pyfinder
```

Use the reviewed `PYFINDER_REPOSITORY` checkout as context if its path differs.
A fresh build cannot obtain an unpublished fix. While the canonical caller is
absent, set integration false, run `make verify-image` and inspect its emitted
`PYFINDER_IMAGE_RESULT`, including `paramws_commit`. Compare it with the release/fix
you intend to deploy. The check validates installed provenance consistency, not
that a commit is newest or contains every required fix. Verify required behavior
separately when accepting a dependency change.

Run `make verify-caller EVIDENCE=/absolute/fresh/evidence-directory`, review queue
and settings, explicitly enable integration, start the caller and run `make verify`.
Existing prepared calculations retain profile, inputs and overwrite policy after
restart. Restarting an old container does not install application/catalog changes.
Do not reset the queue or delete runtime data for an upgrade.

## Logs and troubleshooting

The terminal identifies the action and delegated helper; component output contains
the underlying diagnostic. Use `make check` for accumulated prerequisites and
`make status` for container state. Neither command changes the deployment.

| Location under this checkout | Contents |
| --- | --- |
| `runtime/shakemap/logs/operations.log` | Host finalization/start phases and outcomes, including precise errors caught by service finalization |
| `runtime/shakemap/logs/service.log` | Entrypoint, API, Uvicorn and runtime diagnostics |
| `runtime/shakemap/.service/events/<id>/logs/service.log` and `shake.log` | Service/native diagnostics for the current calculation |
| `runtime/shakemap/.service/archive/<id>-<UTC>/service/logs/` | Preceding calculation logs retained with `overwrite=false` |
| `runtime/pyfinder/logs/` and run/playback paths printed by PyFinder | Caller process, calculation and provider diagnostics |
| Fresh evidence directory supplied to `verify-caller` | Probe `stdout.log`, `stderr.log` and `summary.json` |

```sh
docker logs --tail 100 shakemap-docker
docker logs --tail 100 pyfinder-docker
tail -n 100 runtime/shakemap/logs/operations.log
tail -f runtime/shakemap/logs/service.log
```

Image-build output stays in the terminal; `operations.log` is a phase history,
not a child-output transcript. Top-level logs append across restarts and are not
archived with calculations, rotated or automatically deleted. Manage retention
while services are stopped, preserving required evidence. See
[service diagnostics](../../shakemap-docker/README.md#service-diagnostics) for access
requirements. A failure before opening a log destination appears on stderr.

| Reported problem | Next step |
| --- | --- |
| Missing image | Build the named component, then repeat its required verification |
| Existing caller occupies probe name | Preserve container-only files; follow the deliberate upgrade procedure before removing it |
| Stale image, environment or mount conflict | Reconcile the canonical container with reviewed settings, preserving mounted data; startup will not silently replace it |
| Missing/unreadable writable path | Correct the exact mount/path and UID/GID access named by the component; use its printed permission-recovery command |
| Missing global asset | Inspect actual runtime, provision only missing assets and validate; resolve invalid existing files deliberately |
| Missing regional reference/module | Follow the exact per-profile path/module diagnostic and native guide; global provisioning does not supply it |

Check the runtime used by this deployment before collecting another copy of a
reported missing file. A file in another checkout does not satisfy its paths.
Keep existing scientific data while investigating; removing a container does not
require deleting its runtime.

## Stop and restart

Stop the caller before the service. Resume a finalized service before the caller.
Stopping preserves containers/data; no restart supervisor or host daemon is
installed. Starting the caller resumes retained scheduled work, including overdue
items, so inspect the queue before activation after a long pause.

## Deliberate scheduler reset

`make reset` permanently deletes all rows in the continuous scheduler's
`runtime/pyfinder/state/scheduled_queries.sqlite3` `event_tracker` table, including
pending, processing and terminal history. It accepts no component or alternate
configuration scope. Stop the canonical caller and all other database writers first:

```sh
make stop COMPONENT=pyfinder
make reset
```

Unknown Docker state, redirected files, an active writer or unfamiliar schema cause
refusal. SQLite handles valid journals transactionally; an absent database creates
no state. Other tables, alert deliveries/evidence, ShakeMap submissions, playback
state, data, products and logs remain. Already accepted ShakeMap jobs and pending
mail are not cancelled. Ordinary startup never performs this reset.

## Real playback

With the compatible canonical caller running and ShakeMap available:

```sh
PYFINDER_ALERT_CONFIG='' PYFINDER_SHAKEMAP_OVERWRITE=false \
  ../pyfinder/scripts/pyfinder playback --event-ids 20230206_0000008
```

Replace the ID as needed. This runs real provider → FinDer → ShakeMap work with
current data availability, not reconstructed historical observations. The launcher
uses the installed caller/shared runtime, refuses an absent/stopped caller and
never starts one automatically. Continuous monitoring remains active and can
process natural alerts during playback.

The example disables email only for this playback and archives preceding ShakeMap
results on ID reuse; other settings inherit the caller. It does not change saved
settings/continuous monitoring or back up caller workspaces. Playback prints its
retained workspace/log/evidence paths and returns nonzero on failure. See
`../pyfinder/scripts/pyfinder playback --help` and
[PyFinder playback](../../pyfinder/README.md#playback) for scheduling and outcomes.
