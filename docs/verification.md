# Deployment verification

Follow the [installation sequence](../README.md) with the project environment
active. These checks answer different questions; host tests, a healthy endpoint
or a listed profile alone cannot establish native or scientific readiness.

## Verification layers and order

| Command from `pyfinder-deploy` | Evidence and effects |
| --- | --- |
| `make test` | Host tests with temporary files, fake commands and a local HTTP stub; no deployed-service certification |
| `make verify-image` | Installed caller imports, identity, build-record consistency and controlled input handling; temporary runtime, network disabled |
| `make verify-caller EVIDENCE=/absolute/fresh/evidence-directory` | Finite installed imports, shared-input access and read-only service requests; transient caller and owned markers |
| `make check` | Read-only accumulated settings, Docker, health/profile and queue diagnostics, including incomplete installations |
| `make verify` | Strict read-only wiring, matching image identities, mounts and settings; both canonical containers must be running |
| `make verify-native` | Component host/container/running-service checks including a fixed native calculation; changes state and may revoke readiness or stop the service |

Successful `make finalize COMPONENT=shakemap` includes global native verification
and leaves the service ready/running. Later `make verify-native` is an explicit
recheck, not another start step. Component repositories own installed-image/native
verification; deployment supplies reviewed settings.

Before activation, keep `PYFINDER_SHAKEMAP_ENABLED=false` and the canonical caller
name absent for `verify-image` and `verify-caller`. A stopped caller still occupies
that name. Preserve necessary container-only files before deliberate replacement
using the [upgrade procedure](installation-and-operations.md#upgrade-the-caller).
Do not enable/start the continuous caller just to make `check` green. Complete
required regional/native tests, review queue/email policy, then explicitly
enable/start and use strict `make verify`.

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

The human report groups issues/actions, successful checks, profile findings,
conditional recovery and evidence limits. JSON supplies the full structured report.
Findings name setting keys, files and resolved service asset paths when available.
Correct the reported resource with its component helper; the checker does not
repair scientific profiles.

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

The caller settings check runs the configured **source checkout**, not the image.
The installed service assesses global and every profile referenced by that catalog
independently. A blocked region with statically usable global recovery remains
conditional/unverified, not silently usable. The installed caller must still
attempt the region and classify an eligible failure before one explicit global
submission. An older service missing the diagnostic API remains unverified. See
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

Choose a new absolute evidence directory **outside runtime**, with an existing
resolved parent. Replace the placeholder before running:

```sh
make verify-caller EVIDENCE=/absolute/fresh/evidence-directory
```

The helper requires disabled integration, an explicit caller URL and an absent
`pyfinder-docker`. It pins image identity, uses the shared parent mount and UID/GID
`1000:1000`, and mounts no host application source. It checks installed import
containment, versions, runtime identity, shared-input read/write access and actual
caller-to-service health/configuration requests. Detailed build-record consistency
belongs to `verify-image`.

The probe creates exclusive owned host/caller markers, then removes them and its
owned transient caller. Protected `stdout.log`, `stderr.log` and `summary.json`
remain in the evidence directory. It does not remove an operator caller or compare
an image with uncommitted source. Ordinary probing does not start the production
listener, run FinDer, query providers or send mail.

## Optional synthetic native calculation

The helper also accepts a fixture. Use fresh owned values for both placeholders:

```sh
./scripts/verify-caller-deployment.sh \
  --evidence /absolute/fresh/evidence-directory \
  --calculation-fixture tests/fixtures/shakemap-global.json \
  --event-id pyfinder-verification-global-UNUSED_t00000
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
