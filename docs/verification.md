# Deployment verification

Follow the [installation sequence](../README.md) with the project environment
active. Each check answers a different question: is the software installed, can
the containers communicate, or can ShakeMap calculate and save a usable result?
One passing check does not answer all three.

## Verification layers and order

| Command from `pyfinder-deploy` | Evidence and effects |
| --- | --- |
| `make verify-image` | Can the built PyFinder image load its installed packages and handle the required shared storage? Uses a temporary container with networking disabled. |
| `make verify-caller EVIDENCE=/absolute/fresh/evidence-directory` | Can a temporary PyFinder container read/write the shared input folder and reach the running ShakeMap service? Saves its report in your evidence directory. |
| `make check` | Which settings, containers, files or queued work still need attention? Reads the deployment without repairing or starting it. |
| `make verify` | Do both running containers use the expected images, mounts and settings? Run after activation. |
| `make test` | Optional developer tests of the source and helpers; requires the application dependencies below. Does not test the deployed service. |
| `make verify-native` | Optional comprehensive ShakeMap recheck: host tests, installed-container checks and a real calculation. Needs extra host test dependencies and can stop the service or mark it unavailable on failure. |

Successful `make finalize COMPONENT=shakemap` already calculates the supplied
global test earthquake inside Docker and leaves ShakeMap running. You do not
need a second start command or `make verify-native` to complete that step.

Ordinary installation needs neither host PyFinder nor host ParamWS. Image and
caller probes import those packages inside Docker. `make check` reads the caller's
source settings without importing its scientific application stack.

## Before activation

Keep `PYFINDER_SHAKEMAP_ENABLED=false` and the `pyfinder-docker` container name
absent while running `verify-image` and `verify-caller`. Even a stopped container
occupies that name. For an existing caller, first preserve its container-only
files and follow the [upgrade procedure](installation-and-operations.md#upgrade-the-caller).

Wait for both checks to finish successfully, then run `make check`. Its combined
report may still say `BLOCKED` because PyFinder is deliberately absent and
integration is disabled. Read the individual findings before deciding what to do:

| Finding before live startup | What to do |
| --- | --- |
| PyFinder container is absent | Expected at this step. Continue after the image and connection checks have passed. |
| Caller source settings are blocked **only because integration is disabled** | Expected. Keep it disabled until the README's activation step. Inspect the component's detailed reason: any other settings error must be corrected first. |
| An existing stopped PyFinder container prevents the temporary checks | Preserve its files and follow the upgrade procedure; do not start it merely to clear the report. |
| ShakeMap is unavailable/not ready, global files are missing/invalid, or image/connection/shared-folder checks fail | Correct the named error and repeat the failed step before starting live processing. |
| Optional regional files or models are missing, broken or not yet checked | You may finish global installation, but that profile is not established as working. Follow its findings and test it separately before relying on regional results. A possible global recovery is not a proven successful calculation. |
| Retained queue contains overdue pending work | Decide whether that work should run when PyFinder starts. Preserve it unless you deliberately choose the separate scheduler-reset procedure. |
| Queue cannot be inspected because it may still be active, or its state is unfamiliar | Identify the writer/state and review it before activation; the check did not clear or validate the queue. |
| Email is configured but delivery is unverified | Review the SMTP account, recipients and intended delivery before enabling operational mail, or leave `PYFINDER_ALERT_CONFIG=` empty to disable it. No test mail is sent by these checks. |
| Obsolete selector warning | The setting is ignored. Remove it when convenient; that warning alone does not block activation. |

When the required checks and queue/email decisions are complete, follow the
README's explicit enable/start step, then run `make verify` with both containers
running. Optional region findings remain visible; starting the caller does not
repair their configuration or guarantee fallback.

## Interpret `make check`

This diagnostic reads literal settings, Docker inventory/inspection, GET service
health/configuration checks and an existing closed operational queue. It does not
build, download, provision, start containers, submit calculations, send email,
change readiness or write queue state. No report is saved automatically.

```sh
make check
./scripts/check-deployment.sh --config /absolute/path/to/deployment.env
./scripts/check-deployment.sh --json
```

The report names each problem, its relevant setting/file/path and the action to
take. It also lists checks that passed and the profiles that still need attention.
Use `--json` when you need the full structured details. Correct the reported
setting or file and rerun the check; it does not repair profiles for you.

| Status | Meaning | Direct helper exit |
| --- | --- | --- |
| `usable` | Inspected static capability has no known blocker | 0 |
| `degraded` | Known limited capability remains usable | 0 |
| `blocked` | Confirmed obstacle, including absent continuous caller or overdue work needing a decision | 1 |
| `unverified` | Required evidence unavailable, including stopped endpoint or unsupported diagnostic API | 2 |

Blocked takes precedence over unverified. Usage errors also return 2. GNU Make
returns 2 when its recipe fails; automation needing the distinction should invoke
`check-deployment.sh` directly. Neither exit 0 nor a listed profile proves native
execution or scientific coverage. Before activation, absent caller and disabled
integration are expected and remain honestly blocked.

The caller settings check reads the configured **source checkout**, not the image.
The running service checks global and every profile named in that routing catalog.
It can report that a regional profile is broken while global has no known missing
prerequisite. That does not prove recovery works: during actual work, PyFinder
must submit the selected region first and confirm a configuration failure before
it may make one separate global request. An older service without the diagnostic
API remains unverified. See
[static profile checks](../../shakemap-docker/docs/configuration.md#read-only-profile-checks).

Email may remain explicitly disabled. Configured or implicitly discovered email
is unverified because this command does not send mail. The obsolete fixed profile
setting only warns; warnings are separately included in human/JSON reports and
alone do not block or degrade checks.

An absent operational database means startup initializes an empty queue. An
existing closed, sidecar-free SQLite snapshot supplies status counts and overdue
pending work; active/uncertain state is unverified. Preserve retained work and
review whether it belongs to this installation before activation. No diagnostic
clears a backlog; [reset](installation-and-operations.md#deliberate-scheduler-reset)
is a separate destructive decision.

## Installed caller image

`make verify-image` delegates to PyFinder's verifier. It uses the canonical name
temporarily and refuses an existing caller. Without network or application source
mounts it exercises installed packages, Python/base-image identity, runtime account,
package origins, recorded ParamWS commit, logging placement and controlled FinDer
input preparation. It does not run native FinDer, query providers or deliver mail.

Retain emitted `PYFINDER_IMAGE_RESULT` and image identity with deployment evidence.
Its `paramws_commit` records the installed dependency source; compare it with the
version/fix intended for deployment. Build-record consistency does not prove the
newest remote revision or every behavior. A cached dependency fetch may survive
ordinary builds; use the deliberate [refresh procedure](installation-and-operations.md#upgrade-the-caller)
when required.

## Finite caller-to-service probe

Run this before starting continuous PyFinder. It creates a temporary container
from the built image and checks that it can read/write the shared input folder
and reach the running ShakeMap service. It then removes that temporary container.
It does not start the earthquake listener, query providers or run FinDer.

Choose a new absolute directory **outside runtime** for the report and logs. Its
parent must already exist, but the chosen directory must not. Replace the
placeholder before running:

```sh
make verify-caller EVIDENCE=/absolute/fresh/evidence-directory
```

The helper requires disabled integration, an explicit caller URL and an absent
`pyfinder-docker`. Its code comes from the installed image, not a mounted host
checkout. The temporary container uses the same shared folder and UID/GID
`1000:1000` as the real caller. This is why a successful host HTTP request alone
cannot replace the check. Image/package version checks also remain separate in
`verify-image`.

It creates uniquely named temporary files to test both sides of the shared
folder, then removes those files and its temporary caller. `stdout.log`,
`stderr.log` and `summary.json` remain in your evidence directory. Continue when
the command succeeds; on failure, read those files and correct the reported
connection, access or package problem before retrying with a new evidence folder.
The helper does not remove an operator's existing caller or send email.

## Optional synthetic native calculation

The helper also accepts a fixture. Choose a new evidence directory as described
above and a calculation ID not previously used on this installation. This helper
requires an ID starting with `pyfinder-verification-` and ending with `_t00000`.
In the example below, change `global-001` to an unused name using letters A–Z/a–z,
digits 0–9, hyphens or underscores; keep the required prefix and suffix. The full
ID must be at most 231 characters. It is your choice, not generated by the helper.
This format is specific to the helper;
ordinary `shake-in-docker submit` IDs do not require it.

```sh
./scripts/verify-caller-deployment.sh \
  --evidence /absolute/fresh/evidence-directory \
  --calculation-fixture tests/fixtures/shakemap-global.json \
  --event-id pyfinder-verification-global-001_t00000
```

The fixture specifies physical UTC origin, coordinates, magnitude, depth and station
PGA in cm/s². Installed manager/exporter code prepares inputs without running FinDer.
The helper requires an idle service and unused ID across input, product, current
record and archive trees. It reserves a new workspace under
`runtime/pyfinder/playbacks/<event_id>/shakemap-verification`, retaining SQLite
intent, observations, logs and evidence separately from the operational database.

It makes one POST and follows the exact acknowledged sequence with bounded polling.
It never retries uncertain acceptance; timeout does not cancel a native job.
Products and failed-run evidence remain; only the transient caller and owned probe
markers are removed. Native execution can make external requests, including STREC.

Success requires validated core products, manifest/hashes, provenance, logs and
selected-profile evidence. `--expect-native FAILED` explicitly checks a known
negative case; matching it does not establish regional readiness. This helper
submits one profile and does not exercise scheduler-owned fallback.

## Check a regional calculation

The [README's regional test](../README.md#5-install-and-test-your-shakemap-profiles)
uses your profile and representative native input files. This performs a real
calculation and retains its output. A static profile check or the global
installation test cannot replace it.

The commands below continue the README's example, `regional-test-001`. If you
submitted a different ID, use that exact name in both `status` and `products`;
these commands look up your calculation rather than choosing a new name.

Save the `internal_sequence` returned by `submit`. That number identifies this
attempt even if the public calculation ID is later reused. Run `status` with
your actual ID and host URL, repeating while the matching job is `QUEUED` or
`RUNNING`:

```sh
shake-in-docker --url http://127.0.0.1:9010 status regional-test-001
```

In `jobs`, find the entry with the saved `internal_sequence`:

| Field in that job | What to check |
| --- | --- |
| `status` | Wait for `SUCCESS` or `FAILED`; queued/running work is not finished. |
| `job_completed` and `products_ready` | Both must be `true` for a usable successful result. `job_completed=true` alone also describes a finished failure. |
| `failure` and `native_outcome` | On failure, read the reported reason and native outcome before correcting inputs or configuration. |
| `shared_paths.service_log` and `shared_paths.shake_log` | Open the printed host paths to read service and native ShakeMap diagnostics. There is no separate CLI `logs` command. |
| `provenance` and `shared_paths.provenance` | Check the record of which configuration, image and input files produced this attempt. Preserve it with the result. |

If the attempt has already been archived, `status` also reports `archives`;
do not substitute a later job with the same public ID. Never repeat a submission
just because its acknowledgement or a later status request was lost. First
establish what happened to the original attempt.

For a successful current job, inspect the product summary:

```sh
shake-in-docker --url http://127.0.0.1:9010 products regional-test-001
```

Check `current.internal_sequence` against the saved number. Require
`current.manifest_state="complete"` and every entry in `current.required_products`
to have `passed=true`. `current.products` lists the produced files and sizes;
`current.shared_paths.product_manifest` names the complete manifest containing
file hashes. The status response provides the logs and provenance paths. Preserve
these records together; merely finding files in a product folder does not show
that this attempt succeeded.

Review the resulting maps and scientific output for the intended event/region.
Passing these software checks does not validate every model branch, geographic
area or future input. After correcting a failed configuration, use a fresh test ID
or deliberately choose the documented archive/replacement policy for an existing one.

## Optional developer host tests

These checks support work on the source and helpers; they are separate from the
operator installation and preactivation sequence. Run from `pyfinder-deploy` with
the existing project environment active.

### Deployment and application fixture tests

`make test` includes a real PyFinder manager/exporter fixture test, so it needs
PyFinder's host scientific dependencies, including ParamWS. For this developer
workflow, the active environment must satisfy PyFinder's Python `>=3.12` metadata.
If your operator environment is older, arrange a suitable developer workspace
deliberately; do not overwrite its `.venv` just to run these optional tests.

```sh
python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else "Developer application tests require Python 3.12 or newer")'
python -m pip install \
  'paramws-clients @ git+https://github.com/pyfinder-dev/paramws-clients.git@master'
python -m pip install -e ../pyfinder
make test
```

Resolve a failed interpreter check or installation before continuing. The explicit
ParamWS source follows the application's dependency policy; do not edit that
dependency checkout. These host tests use temporary files, fake commands and a
local HTTP stub. They do not run native FinDer or certify a deployed service.

### Comprehensive ShakeMap recheck

`make verify-native` retains the component's three stages: its full host test
suite, container-internal checks and running-service/native verification. Install
the ShakeMap host test requirements first; this does **not** need host PyFinder
or ParamWS:

```sh
(cd ../shakemap-docker && python -m pip install -r requirements.txt)
make verify-native
```

The command expects the finalized canonical ShakeMap service to be running. It
submits a fixed verification calculation and can change readiness or stop the
service on failure; use it deliberately, with its component guide's prerequisites.
Ordinary `make finalize COMPONENT=shakemap` already performs container-internal
and global native verification without running the host test suite. Neither
command qualifies your regional science by itself.

## Evidence limits

Global readiness does not qualify regional profiles, every geographic branch or
scientific accuracy. Regional modules, grids, original polygons and native settings
need their own checks; missing optional inputs do not prevent global installation
or startup. Runtime-only changes are not reproduced by a fresh checkout. See
[native configuration](../../shakemap-docker/docs/configuration.md).

Finite checks do not establish actual provider acquisition, FinDer results,
scheduler recovery, notification delivery or operational supervision. Use
[explicit playback](installation-and-operations.md#real-playback) and separate
boundary evidence as needed. Playback executes real work while continuous
monitoring remains active; it is not isolated or a historical replay.

A passing fixture applies to that fixture, selected profile, data and image.
Retain image/dependency identity, logs and native evidence when accepting a
deployment; later code/data changes need the relevant verification again.
