# PyFinder deployment

This repository connects the PyFinder application and separate ShakeMap service
on one host. Component repositories own their images, scientific behavior and
service helpers. These scripts configure and delegate those helpers; they do not
replace either workflow or install the legacy combined `pyfinder-docker` image.

This is an initial deployment foundation. It does not establish complete workflow
readiness: broader regional verification, reproducible regional provisioning,
exact-calculation product retention, uncertain-submission recovery and notifications
still need separate work. The complete scheduled production chain has not been
verified by the finite checks.

## Prepare local settings

Use the existing project environment for every host command:

```sh
source /Users/savas/my-codes/eew/pyfinder-dev/.venv/bin/activate
cd /Users/savas/my-codes/eew/pyfinder-dev/pyfinder-deploy
make setup
```

Setup preserves an existing `deployment.env` and all existing runtime contents.
It creates only missing PyFinder directories and copies the example settings when
no local file exists. It does not change ownership, install packages, download
data, build images, migrate files or start containers. Review `deployment.env`.
Use literal `KEY=value` lines: no quotes, `export`, substitutions or inline
comments. Spaces inside paths are supported. Local settings, runtime contents and
the operational exchange file are ignored by Git; durable `.agent` files are not.

Optional `PYFINDER_ALERT_CONFIG` selects the existing separate email configuration
file by its container path under `/home/sysop/runtime/pyfinder`. Deployment
validates that it maps to an existing regular file in the current parent bind;
it does not read credentials or add a mount. Empty explicitly disables email;
omitting the key preserves PyFinder's legacy file discovery. The example disables
email. Keep secrets and recipients in the separate file, never `deployment.env`.
The wrapper ignores an ambient shell override, so local settings remain decisive.

The approved runtime is this repository's
`/Users/savas/my-codes/eew/pyfinder-dev/pyfinder-deploy/runtime`. PyFinder owns
`runtime/pyfinder`; ShakeMap owns `runtime/shakemap`. The example sets this common
parent explicitly and keeps caller integration disabled. Setup only prepares
missing caller directories/settings; migration and container verification are
separate operations.

## Current deployment state

On 2026-09-26, the former development runtime was consolidated at
`/Users/savas/my-codes/eew/pyfinder-dev/pyfinder-deploy/runtime`. Existing PyFinder
files were preserved, as were ShakeMap datasets, calculations, archives and the
historical `install-dtgeo` payload. The old source-repository runtime was removed
after verification; no second empty runtime was substituted.

Canonical ShakeMap is running and reports ready with version 4.4.9 and its
unchanged image. Its parent bind uses the consolidated root, with the existing
read-only global/regional/test data overlays. Retained current sequences 3, 4 and
7 and archived sequence 6 remain accessible with products ready. The migration
did not execute another scientific calculation or establish regional readiness.

Four operational status records had their six shared-path fields rebased to the
new host root, with original records backed up. Scientific files and historical
provenance retain their original content; older paths inside historical evidence
identify where those calculations were made and are not active deployment settings.
Protected evidence is retained at
`/private/tmp/pyfinder-runtime-migration-20260926`; begin with `summary.json` rather
than distributing raw Docker inspection files, which can contain environment data.

PyFinder was rebuilt and verified on 2026-09-26. Image `sha256:3e55e5d552f0...`
uses Python 3.12.13 and recorded ParamWS commit
`3ddb2aaf08a798465d415f37828ad2dfce155043`. Isolated image checks passed, followed
by the finite installed-caller probe: all 13 selected module hashes matched the
current checkout, package origins were installed site-packages, and UID/GID 1000:1000
verified two-way shared-input access and REST connectivity to ready ShakeMap 4.4.9.
The selected `global` configuration was listed; this did not run a native job.
Exact image/provenance and probe results are in
`/private/tmp/pyfinder-caller-boundary-20260926/summary.json`.

The transient caller and its markers were removed after verification. Canonical
`pyfinder-docker` is currently absent, local integration remains false, and all
1,574 preexisting PyFinder runtime files were preserved. No listener, provider,
operational database, FinDer or SMTP workflow was run. The service queue remained
empty. Production activation still requires a separate reviewed step.


Fresh synthetic calculations subsequently ran from that installed caller image
on 2026-09-26. These outcomes apply to the explicit point fixtures and the runtime
profiles/data used for this pass:

| Configuration | Sequence | Native outcome and verification | Saved evidence |
| --- | --- | --- | --- |
| global | 8 | SUCCESS; corrected validator passed GET-only revalidation with runtime mounted read-only | `/private/tmp/pyfinder-native-global-20260926-r1-revalidation/summary.json` |
| belgium | 9 | Expected FAILED; legacy VS30 path and missing-layer diagnostics retained, no fallback | `/private/tmp/pyfinder-native-belgium-20260926-r1/summary.json` |
| france | 10 | SUCCESS; full product/profile evidence passed | `/private/tmp/pyfinder-native-france-20260926-r1/summary.json` |
| croatia | 11 | SUCCESS; full product/profile evidence passed | `/private/tmp/pyfinder-native-croatia-20260926-r1/summary.json` |
| slovenia | 12 | SUCCESS; full product/profile evidence passed | `/private/tmp/pyfinder-native-slovenia-20260926-r1/summary.json` |

All four successful calculations passed validation of 27 products, required core
products, hashes/sizes, logs, provenance and 11 profile-file identities. The first
global run exposed a verifier schema error after native SUCCESS: detailed job
rows intentionally omit the enclosing event ID. Its original harness failure is
preserved at `/private/tmp/pyfinder-native-global-20260926-r1/summary.json`.
The corrected validator checked the existing sequence; global was not resubmitted.
Belgium's expected-failure assertion passed, which is evidence of visible failure
without fallback, not Belgian readiness.

Only the Croatia, France and Slovenia runtime profiles received the bounded
corrections in this pass: 21 mechanical configuration-key changes and 21
byte-preserved layer copies. The exact INGV-linked regional grid was imported;
its observed identity is 611,360,031 bytes, SHA-256
`5eb72b040ac1c3a10ec4333b8eeb1b0234637219496d82bf6368d47cf0c1ab3a`.
A publisher checksum, grid version and license were not verified from that link.
This observed transfer identity does not prove equality with a formerly missing
original asset. Correction/backups and semantic differences are recorded under
`/private/tmp/pyfinder-regional-correction-ts0jiilh`.

The fixture helper verifies regional profile bytes and records the selected data
paths. Separate read-only postchecks found the expected effective VS30 filename
in each successful native `shake_result.hdf` and confirmed the regional grid still
matched its pre-import observed identity; global topography matched its managed
manifest. The HDF configuration did not contain the topography setting. Evidence
is in `/private/tmp/pyfinder-native-matrix-20260926-r1/`:
`native-hdf-effective-configuration.json` and `postrun-asset-identities.json`.
These checks are not a hidden per-calculation validation feature. One successful
point does not validate every regional branch, coverage or scientific accuracy. Albania, Belgium, Greece, Italy, Romania and Switzerland still lack a
successful current-profile verification and have unresolved configuration/assets.
These regional corrections currently live in ignored operator runtime settings;
repeatable, versioned regional provisioning remains development work. A fresh
checkout alone cannot reproduce this operator state.

Final cleanup and preservation checks are recorded in
`/private/tmp/pyfinder-native-matrix-20260926-r1/summary.json`: the caller is absent,
probe markers are gone, integration remains false, the same ShakeMap container is
ready with an empty queue, and all 1,574 preexisting caller files plus 749 older
service-calculation files are unchanged. Only the new owned fixture workspaces and
service results were added. No PyFinder provider acquisition, FinDer, SMTP or
production listener ran. Native STREC attempted online tensor lookup for the
synthetic event IDs; these native runs must not be described as having zero outbound
network activity.

## Configure the shared boundary

`SHAKEMAP_RUNTIME_ROOT` must equal the approved common parent. External runtime
roots are refused before component commands run. Both supported container
configurations bind that same host parent to `/home/sysop/runtime`, so the caller setting
`/home/sysop/runtime/shakemap/data/inputs` reaches the service's canonical inputs.
There is no additional input bind or launcher-only input-source setting.

The full parent mount makes both component trees visible to both containers.
This is shared storage with application ownership, not filesystem access isolation:
PyFinder writes its own subtree and prepares its agreed event inputs; ShakeMap
owns its calculation products, records and data handling. The service's existing
read-only global/regional/test data overlays protect its view, not the caller's
view. Do not interpret visibility as permission to modify another component's
files. Retained historical payloads such as `install-dtgeo` are not automatically
activated or selected as scientific data.

Existing containers are never removed or recreated by these wrappers. Their image,
settings or mounts may need deliberate replacement while preserving mounted data.
The rebuilt caller image passed installed-code and bounded connectivity checks;
these checks must be repeated when relevant code, image or deployment settings
change. The previous caller image ID became unresolvable after tag replacement;
retained old inspection and container-only GMT files are evidence, not a runnable
rollback image. The concise record is
`/private/tmp/pyfinder-image-verification-20260926/rollback-limitation.txt`.
Do not assume the old image can be restarted.

The example caller endpoint is `http://host.docker.internal:9010`, explicitly
selected for this Docker Desktop host and verified by the 2026-09-26 finite
installed-caller probe. Recheck it after routing changes. Host `127.0.0.1` is not
container loopback. Linux
would need its own verified host-gateway or network arrangement; this foundation
does not add one or infer routing from a successful host HTTP request.

The six `PYFINDER_SHAKEMAP_*` application settings retain the
[PyFinder adapter semantics](../pyfinder/docs/shakemap-adapter.md). The caller
selects the initial explicit configuration, with `global` as the default.
The service never substitutes configurations. PyFinder's bounded caller policy
first submits the selected region and, only after confirmed configuration failure
and retained evidence, may submit `global` once with the same public ID and a new
sequence. It preserves overwrite and reports both outcomes; uncertain acceptance
or unrelated native failure does not authorize another submission.
`overwrite=true` recalculates a reused public calculation ID after discarding its
previous service/product trees; false archives them. The wrapper does not invent
IDs, infer regions, schedule calculations or modify scientific defaults.

Both processes need actual UID/GID 1000:1000 access to shared inputs. Host file
ownership alone, particularly on Docker Desktop, does not prove this access.
Helpers do not recursively chmod/chown existing operator data.

## Operator commands

Bare `make` displays help. Mutation commands require an explicit component.
Nothing starts continuous operation as a side effect of setup, build or verify.

| Command | Responsibility and side effects |
| --- | --- |
| `make setup` | Preserve/create local settings and missing PyFinder directories |
| `make build COMPONENT=pyfinder` | Build `pyfinder:dev` from the component Dockerfile, `linux/amd64`; retains required FinDer base |
| `make build COMPONENT=shakemap` | Delegate canonical ShakeMap image build |
| `make data COMPONENT=shakemap DATA_ACTION=inspect` | Read-only asset presence/readability inspection |
| `make data COMPONENT=shakemap DATA_ACTION=validate` | Read-only pinned asset validation; may hash large files |
| `make data COMPONENT=shakemap DATA_ACTION=provision` | Explicitly download/import missing assets using the service helper |
| `make finalize COMPONENT=shakemap` | Explicit service finalization; can create/recreate canonical container and perform native verification |
| `make start COMPONENT=shakemap` | Start an already finalized, compatible canonical service |
| `make start COMPONENT=pyfinder` | Start continuous EMSC/provider/FinDer processing with explicitly enabled REST integration |
| `make stop COMPONENT=pyfinder` | Stop caller without deleting its container or mounted data |
| `make stop COMPONENT=shakemap` | Delegate the service's graceful-stop boundary |
| `make status` | Read-only canonical Docker state; not scientific readiness |
| `make verify` | Read-only host paths, health/configuration GETs, image identity, mounts and caller settings |
| `make verify-live COMPONENT=shakemap` | **Mutating:** native fixture submission; component helper may revoke readiness and stop service on failure |
| `make verify-live COMPONENT=pyfinder` | Component installed-image verification; refuses an existing canonical caller container |
| `make verify-caller EVIDENCE=/absolute/fresh/directory` | Finite installed-caller imports, shared-input access and read-only REST connectivity; refuses any existing canonical caller |
| `make test` | Host tests with temporary files, fake component commands and an isolated HTTP stub |

Use the corresponding `scripts/*-deployment.sh --help` for direct invocation and
`--config /absolute/path/to/settings` for a reviewed alternate local settings file.
Component helpers run from their own repository directories, using the activated
project environment. For manual dataset imports and additional data-helper options,
use the service's `scripts/manage-shakemap-data.sh` directly with explicit
`--runtime /Users/savas/my-codes/eew/pyfinder-dev/pyfinder-deploy/runtime`;
this repository does not duplicate its download/checksum/repair implementation.

Use these deployment helpers for normal operations after the completed move. The service
repository's bare Make/helper defaults still point at its old development
`runtime`; they are not redirected silently. Direct service startup/finalization
must explicitly use `--runtime-root` with the approved deployment runtime. Do not
initialize a second empty runtime at the former location. The wrappers always
pass the canonical path and reject an external root.

Start the service before the caller. Stop the caller first when pausing both.
No automatic restart policy or daemon has been added. Keep successful host tests,
container-internal checks and real running-service evidence separate. The default
preflight does not prove caller network reachability, actual UID write access,
installed adapter capability, successful FinDer execution or regional scientific
validity. In particular, configuration listing alone is not a native regional run.

Setup and ordinary startup do not perform runtime migration or automatic container
replacement. Explicit service finalization has the mutating behavior listed above.
The completed migration evidence is recorded separately; production caller
activation remains disabled until reviewed.


## Verify the installed caller without activating production

First rebuild current PyFinder through `make build COMPONENT=pyfinder`. Its
Dockerfile retains `FROM ghcr.io/sceylan/finder-base:gmt5`, verifies the downloaded
Python archive checksum, clones ParamWS over HTTPS and records that exact commit.
Do not bypass TLS or certificate failures to complete a build. A successful build
with unpinned dependency versions is evidence for that recorded image, not a claim
that every future build will resolve identical dependencies.

For a future replacement, preserve any existing canonical caller's inspection
and container-only files before its explicitly authorized removal. Both verification helpers refuse an
existing `pyfinder-docker`; neither removes an unrelated instance or invents an
alternate name. Run `make verify-live COMPONENT=pyfinder` for the existing isolated
installed-image checks. They keep `--network none` and temporary runtime storage.

Then, while the canonical caller name is absent and integration remains disabled:

```sh
make verify-caller EVIDENCE="/private/tmp/pyfinder-caller-boundary-<fresh-label>"
```

Choose a new evidence directory each time. The direct equivalent is
`scripts/verify-caller-deployment.sh --evidence /absolute/fresh/directory`, with
optional `--config /absolute/deployment.env`. This uses the existing project
virtual environment and a transient canonical caller pinned to the inspected
immutable image ID, running as UID/GID1000:1000. It mounts only the consolidated
runtime parent and sends finite verification code on stdin to isolated installed
Python; it does not mount application source or start the continuous entrypoint.

The probe compares installed module hashes against the current checkout, verifies
package/ParamWS origins and recorded build provenance, checks the selected service
configuration via read-only health/configuration requests, and proves two-way
visibility of uniquely owned temporary input markers. It removes only its own
markers and exact CID/label-owned transient container, including after failure.
A changed ownership check leaves that resource untouched with a diagnostic.
Evidence is retained in a private directory; inspect `summary.json` and protected
process logs for failed or timed-out checks.

By default, no EMSC listener, provider acquisition, operational database, FinDer,
SMTP or native ShakeMap calculation is invoked. The canonical caller is absent after successful
verification. These checks establish installed caller code, shared input access
and connectivity for the inspected image/settings; they do not enable production,
validate regional scientific coverage, or certify the full scheduled workflow.


For an explicitly requested synthetic native calculation, use the same finite
helper with a fixture and a new public calculation ID:

```sh
scripts/verify-caller-deployment.sh \
  --calculation-fixture tests/fixtures/shakemap-global.json \
  --event-id "pyfinder-verification-global-<fresh-label>_t00000" \
  --evidence "/private/tmp/pyfinder-native-global-<fresh-label>"
```

Replace both placeholders before running. This option **submits one native job**;
it is never enabled by `make verify-caller`. The fixture names its configuration
explicitly. The supplied global point fixture is synthetic: UTC origin
`2026-09-26T12:30:15.250000Z`, magnitude 5.5, depth 6 km, latitude 42.05 and
longitude 13.0, with two station components at 42.02/13.02 reporting PGA
98.0665 cm/s² (10 percent of standard gravity). The fixture schema accepts
only those explicit event values, `synthetic: true`, `configuration`, and station
`network`, `station`, `location`, `channel`, `latitude`, `longitude`, `pga_cm_s2`.
Coordinates use degrees and positive depth uses km. Installed manager/exporter
classes prepare the point inputs without running FinDer or acquiring observations.

The helper requires an idle service and checks API/current/input/product/archive
ownership before submission. It exclusively reserves
`runtime/pyfinder/playbacks/<event_id>/shakemap-verification/`; an existing parent
calculation directory is rejected. The fixture inputs, submission SQLite database,
acknowledgement, observations, native logs and validation evidence remain there.
SQLite access is limited to this workspace, and the existing parent mount is the
only bind. The operational database remains unopened. One POST is permitted;
an uncertain acknowledgement is retained and never retried. Polling follows the
exact acknowledged sequence for at most ten minutes; the finite container has a
13-minute outer deadline. Timeout/container termination does not cancel the native
service job. Inspect the retained intent, observations and service state before
any further action; do not reuse the ID or evidence directory.

Native `SUCCESS` must pass the full product manifest and core-product gate, every
product hash/size, provenance, logs and exported-input snapshot checks. Selected
profile file identities are verified; regional materialization must match the
explicit regional source files byte for byte. The global profile must reference
its canonical managed VS30/topography files and their recorded hashes must match.
These checks record dataset declarations and selected paths, but do not claim an
independent observation of native dataset use or validate scientific accuracy.

Regional fixtures use the same helper and units with an explicitly selected
configuration. The current controlled verification matrix is:

| Fixture | Expected native outcome | Additional option |
| --- | --- | --- |
| `tests/fixtures/shakemap-global.json` | SUCCESS | Default |
| `tests/fixtures/shakemap-belgium.json` | FAILED, unchanged profile negative check | `--expect-native FAILED` |
| `tests/fixtures/shakemap-france.json` | SUCCESS, corrected profile | Default |
| `tests/fixtures/shakemap-croatia.json` | SUCCESS, corrected profile | Default |
| `tests/fixtures/shakemap-slovenia.json` | SUCCESS, corrected profile | Default |

The 2026-09-26 outcomes and their limits are recorded in Current deployment state
above. Future runs must assert their own results with the then-current profiles
and assets. Choose a fresh profile-specific ID and evidence directory for every invocation.
A matched failure means the explicit failure assertion passed; it never means
regional readiness. No global fallback or configuration repair is attempted.
Harness/evidence failures are distinct and remain nonzero even when native
`FAILED` was observed. The helper retains all fixture/service results for review,
including failures, and cleans only its transient caller and input markers.
No production listener, provider, FinDer or SMTP workflow is started by this mode.

For the five regional native files, supported data helpers and current
Italy/Switzerland prerequisites, see the service-owned
[configuration runbook](../shakemap-docker/docs/configuration.md).
