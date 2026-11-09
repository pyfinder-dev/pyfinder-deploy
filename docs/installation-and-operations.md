# Installation and operations

Follow the [README installation sequence](../README.md) for the normal path.
This guide supplies prerequisites, configuration details and recovery procedures.
Commands run from `pyfinder-deploy` unless stated otherwise.

## Host prerequisites

Provide Docker with a working daemon, Bash, Make, Git and an installed Python 3.12
or newer. PyFinder requires at least 3.12; the standalone ShakeMap host package's lower
minimum is insufficient for combined checks. The examples use `python3.12`;
substitute your installed Python 3.12+ command when creating the environment.

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
python3.12 -m venv .venv
```

Activate it, confirm that `python` resolves inside your workspace's `.venv` and
reports Python 3.12 or newer, then enter the deployment checkout:

```sh
source .venv/bin/activate
command -v python
python --version
cd pyfinder-deploy
```

Install host dependencies into this active environment, using official ParamWS
source rather than modifying a local dependency checkout. Resolve any failed
installation command before continuing:

```sh
python -m pip install \
  'paramws-clients @ git+https://github.com/pyfinder-dev/paramws-clients.git@master'
python -m pip install -e ../pyfinder
(cd ../shakemap-docker && python -m pip install -r requirements.txt)
```

PyFinder's checks import its manager and scientific dependencies; installing only
the ShakeMap client is insufficient. ShakeMap's requirements install its editable
host package, `shake-in-docker` and host test dependencies. Host installation does
not install FinDer. Use `../pyfinder/scripts/pyfinder` to run workflows through the
application container.

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

`PYFINDER_SHAKEMAP_URL` must be reachable from the caller container. Docker Desktop
commonly provides `host.docker.internal`; other hosts need an explicitly configured
route. Helpers do not add a host-gateway mapping. A successful host HTTP request
does not prove caller connectivity; use the finite caller probe. Keep
`PYFINDER_SHAKEMAP_ENABLED=false` until verification and queue review are complete.

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

The deployment data target manages pinned global VS30 and topography:

| `DATA_ACTION` | Effect |
| --- | --- |
| `inspect` | Cheap presence/readability inventory |
| `validate` | Full pinned checksum validation without writing |
| `provision` | Install missing assets; reuse valid ones and refuse invalid existing ones |
| `stage` | Validate replacements without activating them |

Use the [service data guide](../../shakemap-docker/docs/configuration.md) for manual
imports and other assets. Direct component commands need this deployment runtime
explicitly: `--runtime` for the data helper and `--runtime-root` for lifecycle
helpers. Their defaults otherwise select the component checkout's runtime.

`make finalize COMPONENT=shakemap` prepares runtime, may replace the canonical
service container and runs fixed global native verification. Success leaves the
service ready and running. Failure can revoke readiness and stop it. Follow the
reported phase/action and exact [permission recovery instructions](../../shakemap-docker/docs/permissions.md)
when needed; do not elevate the entire finalizer or delete runtime data to fix
access. Ordinary startup does not migrate data or replace incompatible containers.
For a stopped compatible deployment, use `make start COMPONENT=shakemap`.

## Regional configuration

PyFinder's installed `regional-configurations` maps arbitrary human region labels
to WKT coverage resources and service profiles. Regions may cross borders, split
an area or share a profile. FinDer's computational catalog is independent.
Selection uses the selected solution location, matching `event.xml`. See
[coverage authoring/provenance](../../pyfinder/docs/shakemap-region-coverage.md).

Uncovered locations use global. Overlaps selecting the same profile select it
once, including borders; conflicting profiles warn and use global. A missing or
unusable optional WKT logs the affected resource and uses global for that calculation
without terminating services. WKT changes require caller rebuild/recreation;
they are separate from service-owned native scientific assets.

Native regional files can be supplied later. Missing optional regional assets
are not global installation/startup prerequisites. The global helper does not
install every regional grid or scientific module. Follow the
[native configuration guide](../../shakemap-docker/docs/configuration.md), inspect
the service's exact reported paths and verify the intended profile separately.
A listed name does not establish valid files, scientific coverage or execution.

The service executes the explicit profile and never substitutes another. PyFinder
first attempts the selected region, then may submit global once after a confirmed
eligible configuration failure. It retains the same public ID, original overwrite
policy and both attempts' evidence. Uncertain acceptance, read failures and unrelated
native failures do not authorize recovery. See the
[adapter guide](../../pyfinder/docs/shakemap-adapter.md). Missing regional files
should produce a precise calculation failure while the service remains usable;
static global checks alone do not guarantee successful recovery.

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

Do not invent replacement scientific data or infer operator dataset absence from
an empty isolated QA runtime. Container removal never requires runtime deletion.

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
