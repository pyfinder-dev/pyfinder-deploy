# PyFinder deployment

Install and operate PyFinder with a separate ShakeMap service on one Docker host.
PyFinder receives alerts, schedules FinDer calculations and submits their inputs;
ShakeMap produces the native maps. This repository configures and invokes the
component helpers through thin Makefile targets.

## 1. Prepare the host

Provide Docker, Bash, Make, Git and Python 3.12 or newer. For a new installation,
choose your own workspace and use the supported sibling layout below. The finite
caller verifier expects `.venv` in that workspace. If you already have these
checkouts or an environment,
[reuse them](docs/installation-and-operations.md#host-prerequisites) instead.

```sh
# Change this example to the host directory you want to use.
PYFINDER_WORKSPACE="$HOME/pyfinder-workspace"
mkdir -p "$PYFINDER_WORKSPACE"
cd -P "$PYFINDER_WORKSPACE"
git clone https://github.com/pyfinder-dev/pyfinder.git
git clone https://github.com/pyfinder-dev/shakemap-docker.git
git clone https://github.com/pyfinder-dev/pyfinder-deploy.git

# Use your installed Python 3.12+ command; create this environment only once.
python3.12 -m venv .venv
source .venv/bin/activate
command -v python
python --version
cd pyfinder-deploy
```

Install the [host dependencies](docs/installation-and-operations.md#host-prerequisites)
into that active environment, then prepare the local settings and runtime:

```sh
make setup
```

All remaining commands run from `pyfinder-deploy` with this environment active.
In each new terminal, return to your checkout and run
`source ../.venv/bin/activate` first; do not create the environment again.

Setup creates missing caller directories and a private `deployment.env`; it
preserves existing settings and data. Both containers share this checkout's
`runtime/` directory. UID/GID `1000:1000` needs access to its writable paths.

## 2. Configure

Edit `deployment.env` and fill its four blank settings:

| Setting | Value to provide |
| --- | --- |
| `PYFINDER_REPOSITORY` | Resolved absolute path to the PyFinder checkout |
| `SHAKEMAP_REPOSITORY` | Resolved absolute path to the ShakeMap checkout |
| `SHAKEMAP_RUNTIME_ROOT` | Resolved absolute path to this checkout's `runtime` directory |
| `PYFINDER_SHAKEMAP_URL` | HTTP(S) service address reachable **from the caller container** |

Use literal `KEY=value` lines, without quotes or shell expansion. Keep
`PYFINDER_SHAKEMAP_ENABLED=false` for the checks below. Keep `PYFINDER_ALERT_CONFIG=`
empty to disable email, or configure it separately before activation. See
[settings and connectivity](docs/installation-and-operations.md#settings-and-connectivity)
for paths, routing and email details.

## 3. Build and initialize ShakeMap

```sh
make build COMPONENT=pyfinder
make build COMPONENT=shakemap

make data COMPONENT=shakemap DATA_ACTION=inspect
# Run provision only when inspection identifies missing global assets.
make data COMPONENT=shakemap DATA_ACTION=provision
make data COMPONENT=shakemap DATA_ACTION=validate

# Prepares runtime and runs native global verification; may recreate the service.
make finalize COMPONENT=shakemap
```

Successful finalization leaves ShakeMap ready and running. Follow a failed
step's diagnostic before proceeding; inspect [logs and recovery guidance](docs/installation-and-operations.md#logs-and-troubleshooting).
Optional regional files may be supplied later and do not block global installation
or service startup. Regional failures remain visible; see
[regional configuration](docs/installation-and-operations.md#regional-configuration).

## 4. Verify before activating PyFinder

Keep integration disabled and the canonical `pyfinder-docker` container **absent**
for the installed-image check and finite caller probe. An existing stopped caller
also occupies that name; use the [upgrade procedure](#upgrade-the-caller) to preserve
its contents before deliberate replacement.

```sh
make test
make verify-image
# Replace with a new absolute directory outside runtime; its parent must exist.
make verify-caller EVIDENCE=/absolute/fresh/evidence-directory
make check
```

`make check` explains missing prerequisites and configuration findings without
changing the deployment. An absent caller and disabled integration are expected
at this stage and still appear as blocked: do not start continuous work merely
to obtain a green report. Review the queue, settings, regional findings and email
policy before activation. [Verification details](docs/verification.md) distinguish
host tests, installed-image checks, running-service checks and native calculations.
Global verification does not qualify every region or the full production chain.

## 5. Activate and operate

After the required checks and queue review, set `PYFINDER_SHAKEMAP_ENABLED=true`
in `deployment.env`, then start PyFinder explicitly:

```sh
# Starts continuous alert reception, provider queries and FinDer processing.
make start COMPONENT=pyfinder
make verify
```

`make verify` requires both canonical containers running and checks their wiring
read-only. Use `make check` for broader diagnostics and `make status` for container
state. To resume a stopped, already-finalized compatible service, run
`make start COMPONENT=shakemap` before starting the caller.

```sh
# Pause the caller before stopping the service. Mounted data is retained.
make stop COMPONENT=pyfinder
make stop COMPONENT=shakemap
```

Use [operations and logs](docs/installation-and-operations.md#logs-and-troubleshooting)
for failures, playback and deliberate scheduler reset. Run `make help` for targets;
helpers accept `--help`. No restart supervisor is installed by these commands.

## Upgrade the caller

Follow the [caller upgrade procedure](docs/installation-and-operations.md#upgrade-the-caller)
to preserve container-only files, rebuild intentionally, verify installed dependency
identity and repeat preactivation checks. Ordinary cached builds may retain an
older fetched dependency. Do not delete runtime data or reset the queue to upgrade.

Component references: [PyFinder workflows](../pyfinder/README.md),
[ShakeMap operations](../shakemap-docker/README.md).
