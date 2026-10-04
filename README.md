# PyFinder deployment

This repository operates PyFinder and the separate ShakeMap service on one host.
PyFinder receives earthquake alerts, schedules FinDer calculations and submits
prepared inputs to ShakeMap. ShakeMap owns native calculations and their products.
Deployment helpers configure and invoke the component helpers; the Makefile is a
set of thin aliases.

## Prerequisites and layout

Provide Docker, Bash, Make and a project Python environment using Python 3.12 or
newer, with the component host dependencies installed. This is PyFinder's minimum;
the standalone ShakeMap service package permits Python 3.10, which is insufficient
for the combined project checks. The helpers do not install these prerequisites,
clone repositories or create a virtual environment. Image builds and data
provisioning require access to their upstream sources; do not bypass TLS or
checksum failures.

Use sibling checkouts with the following layout. Commands below run from
`pyfinder-deploy` after activating the existing parent environment.

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

Install the ShakeMap host package in that environment so its `shake-in-docker`
command is available to the service helpers:

```sh
# From pyfinder-deploy, use the existing project environment.
source ../.venv/bin/activate
python -m pip install -e ../shakemap-docker
```

This installs the host REST client and helper dependencies, not the native FinDer
executable. FinDer runs only inside its required container image.

The canonical images are `pyfinder:dev` and `shakemap-docker:latest`; their container
names are `pyfinder-docker` and `shakemap-docker`. PyFinder retains the required
FinDer base image, `ghcr.io/sceylan/finder-base:gmt5`. The legacy combined container
repository is not part of this installation.

## Configure the deployment

```sh
# From the deployment checkout, activate the already provisioned environment.
source ../.venv/bin/activate

# Create missing caller directories and copy the settings template if absent.
make setup

# Print resolved paths to copy into the three required host-path settings.
(cd ../pyfinder && pwd -P)
(cd ../shakemap-docker && pwd -P)
(cd runtime && pwd -P)
```

Edit `deployment.env` before other operations. Setup preserves an existing file
and runtime contents. The [example](deployment.env.example) deliberately leaves
required host paths and the caller endpoint blank; it is a template, not a working
deployment configuration. Fill `PYFINDER_REPOSITORY`, `SHAKEMAP_REPOSITORY` and
`SHAKEMAP_RUNTIME_ROOT` with the resolved absolute paths printed above. The runtime
must be this deployment checkout's `runtime` directory.

Settings are literal `KEY=value` lines. Do not use quotes, `export`, inline comments,
`~`, `$HOME`, `$PWD` or shell substitutions: the parser does not expand them. Paths
may contain spaces. Unknown, duplicate and missing required settings are rejected.

Set `PYFINDER_SHAKEMAP_URL` to an HTTP(S) endpoint reachable **from the caller
container**. Docker Desktop commonly provides `host.docker.internal`; other Docker
hosts need an explicitly configured route. These helpers do not add a host-gateway
mapping or infer container connectivity from a successful host request. Keep
`PYFINDER_SHAKEMAP_ENABLED=false` until verification is complete.

The selected configuration defaults to `global`. The service always executes the
explicit selection and never infers a region or substitutes another profile.
PyFinder can retain a confirmed regional configuration failure and submit once
more explicitly with `global`, using the same public calculation ID and a new
native sequence. Uncertain acceptance, read failures and unrelated native failures
do not authorize that recovery. Both attempts remain visible in retained evidence
and diagnostics. See the [adapter guide](../pyfinder/docs/shakemap-adapter.md).

`PYFINDER_SHAKEMAP_OVERWRITE=true` replaces the preceding calculation's complete
service and product trees when its public ID is reused; `false` archives both
before recalculation. Neither option updates an old result file by file.

Optional `PYFINDER_ALERT_CONFIG` selects the existing separate email configuration
by its container path under `/home/sysop/runtime/pyfinder`. The mapped file must
exist without symlinks. Empty disables email; omitting the key preserves PyFinder's
legacy configuration discovery. The example disables email. Keep credentials and
recipient lists in the separate file, never in `deployment.env`. See
[PyFinder notification configuration](../pyfinder/README.md).

## Build, prepare data and start

```sh
# Build the two canonical images from the configured component checkouts.
make build COMPONENT=pyfinder
make build COMPONENT=shakemap

# Inspect existing global assets before explicitly provisioning missing data.
make data COMPONENT=shakemap DATA_ACTION=inspect
make data COMPONENT=shakemap DATA_ACTION=provision
make data COMPONENT=shakemap DATA_ACTION=validate

# Prepare and verify the service; this can recreate its canonical container
# and run native verification calculations.
make finalize COMPONENT=shakemap

# Start an already finalized, compatible service when it is stopped.
make start COMPONENT=shakemap

# Inspect service state before the separate verification steps below.
make status
```

The deployment data helper manages the pinned global VS30 and topography assets.
`inspect` reads presence/readability, `validate` verifies identities without writing,
`provision` installs missing assets, and `stage` validates replacements without
activating them. For manual imports, additional assets and regional prerequisites,
use the [service data and configuration guide](../shakemap-docker/docs/configuration.md).
Direct component commands must receive this deployment runtime explicitly:
`--runtime` for the data helper and `--runtime-root` for service lifecycle helpers.
Their defaults otherwise refer to the component checkout's own runtime.

Finalization is a mutating operation. It may create or replace the canonical
service container and publish readiness only after its verification succeeds.
Failure can revoke readiness and stop the service. Ordinary setup and startup do
not migrate runtime data or silently replace incompatible containers. Resolve
reported image, environment or mount conflicts deliberately while preserving
mounted data.

## Shared storage and ownership

Both containers bind the same host `runtime` parent to `/home/sysop/runtime`.
The caller prepares inputs at `/home/sysop/runtime/shakemap/data/inputs`; there is
no additional input bind. UID/GID `1000:1000` must have actual access to the required
writable paths. Setup does not recursively change ownership or permissions.

PyFinder owns `runtime/pyfinder`, including its state, logs, runs and playback
workspaces. ShakeMap owns `runtime/shakemap`, including data, native products and
internal service records. The shared parent exposes both trees to both containers;
application ownership is not filesystem isolation. ShakeMap's global, regional and
test dataset overlays are read-only in the service container. They do not make the
caller's view read-only or authorize it to modify service datasets.

## Verify before continuous operation

Keep host tests, installed-image checks and running-service checks separate.
Container state, a healthy service and a listed configuration each answer different
questions. Configuration listing alone does not validate its scientific modules,
datasets, coverage or native execution.

Keep caller integration disabled and the canonical caller name absent while
running the installed-image check, then the finite caller probe. Complete any
required native fixture checks before proceeding to continuous activation below.
`make verify` inspects existing containers and therefore belongs after both have
been created; it does not replace these pre-activation checks.

| Command | What it checks and changes |
| --- | --- |
| `make test` | Host tests using temporary files, fake commands and a local HTTP stub; no deployment readiness claim |
| `make verify` | Read-only host paths, service health/configuration, image identity, mounts and settings; both canonical containers must already exist |
| `make verify-live COMPONENT=pyfinder` | Installed-image checks with network disabled and temporary runtime; requires the canonical caller name to be absent |
| `make verify-caller EVIDENCE=/absolute/fresh/evidence-directory` | Finite installed imports, shared-input access and read-only REST checks; creates a transient canonical caller and owned input marker, then removes both |
| `make verify-live COMPONENT=shakemap` | Native fixture verification; changes service state and can revoke readiness/stop the service on failure |

Use a new absolute evidence directory outside runtime for each caller probe. The
helper refuses an existing `pyfinder-docker`, pins the image identity, uses the
canonical parent mount and UID/GID, and does not mount application source to hide
packaging defects. It reports the installed package versions, module origins and
image identity while checking the required interfaces. It does not compare those
files with an uncommitted checkout or establish that an image contains the latest
source changes. Rebuild intentionally when deploying changes. Preserve any
existing caller's necessary container-only files before a deliberate removal;
verification does not perform that removal for you.
The ordinary caller probe does not run the production listener, FinDer, provider
queries or email delivery.

For an explicit synthetic native calculation, use the optional fixture mode:

```sh
# Replace both placeholder values with fresh, explicitly owned values.
./scripts/verify-caller-deployment.sh \
  --evidence /absolute/fresh/evidence-directory \
  --calculation-fixture tests/fixtures/shakemap-global.json \
  --event-id pyfinder-verification-global-UNUSED_t00000
```

The fixture supplies a physical UTC origin, coordinates, magnitude, depth and
station PGA in cm/s². Installed manager/exporter code prepares the inputs without
running FinDer. The helper requires an idle service and an unused ID across inputs,
products, current records and archives. It reserves a new playback workspace under
`runtime/pyfinder/playbacks/<event_id>/shakemap-verification` and keeps its SQLite
intent, observations, logs and evidence separate from the operational database.

The helper makes one POST and follows the exact acknowledged sequence with bounded
polling. It never retries uncertain acceptance. A timeout does not cancel a native
job. Results and failed-run evidence are retained; only the transient caller and
owned probe markers are removed. Native calculations can make their own external
requests, including STREC lookups.

Successful verification requires the product manifest, core products, hashes,
provenance, logs and selected-profile evidence. An explicit `--expect-native FAILED`
asserts a known negative test; it never establishes regional readiness. This helper
submits one selected configuration and does not exercise scheduler-owned fallback.

## Activate and stop continuous operation

After the required verification and configuration review, set
`PYFINDER_SHAKEMAP_ENABLED=true` and start the caller:

```sh
# This starts continuous alert reception, provider queries and FinDer processing.
make start COMPONENT=pyfinder

# Once both canonical containers exist, inspect their configured wiring.
make verify

# When pausing both components, stop the caller before the service.
make stop COMPONENT=pyfinder
make stop COMPONENT=shakemap
```

Stopping does not delete containers or mounted data. The helpers do not add
restart supervision or a background host daemon.

## Limits and further configuration

Global readiness does not certify a regional profile or scientific accuracy.
Italy and Switzerland require their own compatible scientific modules, regional
data and configuration checks described in the service guide. Runtime-only profile
changes are not automatically reproduced by setup or a fresh checkout. A successful
fixture applies to that fixture, profile, data and image; it does not validate every
geographic branch or the full scheduled production chain.

Finite caller checks do not establish actual provider acquisition, FinDer results,
scheduler recovery, notification delivery or operational supervision. Validate
those boundaries separately before relying on continuous operation. Build inputs
can also change upstream; retain the actual image and recorded dependency identity
when reproducibility matters.

Run `make help` for aliases. Operational wrappers and the caller verifier accept
`--help` and, where applicable, `--config /absolute/path/to/deployment.env` for alternate literal
settings. The component documentation remains authoritative for
[PyFinder workflows](../pyfinder/README.md) and
[ShakeMap service operations](../shakemap-docker/README.md).
