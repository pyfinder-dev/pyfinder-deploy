# PyFinder deployment

This guide installs two Docker containers. **PyFinder** receives earthquake alerts,
collects observations, runs FinDer and sends its selected solution to **ShakeMap**.
ShakeMap calculates the requested maps and saves the results and logs. You choose
the regions, scientific configurations and external datasets for your workflow.

Follow the steps below from a new installation through live operation. Existing
installations should follow [the upgrade procedure](#upgrade-the-caller) before
replacing a container; keep their settings, data and queued work.

## 1. Prepare your workspace and host tools

You need Docker with a working daemon, Bash, Make, Git and Python 3.11 or newer.
Python on the host runs the management tools. The earthquake calculations and
application dependencies, including ParamWS, run inside Docker. FinDer is supplied
through the required `ghcr.io/sceylan/finder-base:gmt5` image.

Choose your own workspace and keep the three checkouts together. The one-time
PyFinder connection check expects a `.venv` environment in their common parent.
Reuse checkouts and an existing compatible environment instead of recreating them.
For a new workspace:

```sh
# Replace this example with your chosen directory.
PYFINDER_WORKSPACE="$HOME/pyfinder-workspace"
mkdir -p "$PYFINDER_WORKSPACE"
cd -P "$PYFINDER_WORKSPACE"
git clone https://github.com/pyfinder-dev/pyfinder.git
git clone https://github.com/pyfinder-dev/shakemap-docker.git
git clone https://github.com/pyfinder-dev/pyfinder-deploy.git
```

Check your installed interpreter before creating the environment. If `python3`
is too old, use your installed Python 3.11+ command in both commands below. Stop
if the version check fails; do not create a replacement over an existing `.venv`.

```sh
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "Use Python 3.11 or newer for host helpers")'
# Run only once, when this workspace has no .venv.
python3 -m venv .venv
source .venv/bin/activate
command -v python
python --version
cd pyfinder-deploy
```

Install the host command-line tools used to manage the service and send requests
to it. This creates the `shake-in-docker` command in your active environment; it
does not install native ShakeMap on the host. The current package also installs
its declared service libraries. Host PyFinder and ParamWS installs are unnecessary.

```sh
python -m pip install -e ../shakemap-docker
```

Prepare the local settings and storage directories:

```sh
make setup
```

Setup creates missing directories and a private `deployment.env`, preserving
existing files. All following commands run from `pyfinder-deploy` with the
environment active. In a new terminal, return here and run
`source ../.venv/bin/activate` again; you do not need to reinstall the tools.

## 2. Set paths and the ShakeMap address

Edit `deployment.env` and fill its four blank settings:

| Setting | What to enter |
| --- | --- |
| `PYFINDER_REPOSITORY` | Absolute path to your PyFinder checkout, from `(cd ../pyfinder && pwd -P)` |
| `SHAKEMAP_REPOSITORY` | Absolute path to your ShakeMap checkout, from `(cd ../shakemap-docker && pwd -P)` |
| `SHAKEMAP_RUNTIME_ROOT` | Absolute path to this checkout's `runtime`, from `(cd runtime && pwd -P)` |
| `PYFINDER_SHAKEMAP_URL` | Host address chosen below, with the published `SHAKEMAP_PORT` |

Copy literal paths into the file, without quotes or shell variables such as
`$HOME`. ShakeMap publishes a port on the Docker host: `SHAKEMAP_PORT`, which is
`9010` by default. Choose the address for your Docker installation:

- **Docker Desktop:** use its host alias. With the default port, put these
  literal lines in `deployment.env`:

  ```text
  SHAKEMAP_PORT=9010
  PYFINDER_SHAKEMAP_URL=http://host.docker.internal:9010
  ```

- **Docker Engine on Linux (not rootless), using the default IPv4 bridge:**
  discover the host's bridge address with this read-only command:

  ```sh
  docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'
  ```

  Copy the returned address into the URL. For example, **if** it returns
  `172.17.0.1`, use `PYFINDER_SHAKEMAP_URL=http://172.17.0.1:9010`.
  Use your actual result; that address is not universal.

If you change `SHAKEMAP_PORT`, use the same port in the URL. Inside PyFinder,
`localhost` or `127.0.0.1` means the PyFinder container itself, not ShakeMap.
Later host-side `shake-in-docker` examples can use `127.0.0.1` because those
commands run on the Docker host. For custom/rootless networking, a remote daemon
or an unexpected bridge result, follow [the connectivity details](docs/installation-and-operations.md#choose-the-shakemap-url)
instead of copying an example address. Step 6 confirms the chosen URL from inside
the PyFinder image after ShakeMap is running.

Keep `PYFINDER_SHAKEMAP_ENABLED=false` until step 7. Leave
`PYFINDER_ALERT_CONFIG=` empty to disable email, or review your notification
configuration before starting live work. Both containers see host `runtime/` as
`/home/sysop/runtime`; their user, UID/GID `1000:1000`, needs access to its writable
directories. See [path and access details](docs/installation-and-operations.md#settings-and-connectivity)
if you need a different host address or permission setup.

## 3. Choose the configurations for your regions

FinDer and ShakeMap make **separate configuration choices**. Review the
FinDer computational profiles for your workflow in `REGIONAL_PROFILES` in
`../pyfinder/pyfinder/finderconfigs/profiles.py`. Each entry connects a complete
FinDer configuration to a coverage file under
`../pyfinder/pyfinder/extern/finder_regional_wkt/`. Review the registered entries
and their scientific settings. Keep the supplied profiles if they fit your
workflow; changing regional selection does not require designing new models.
Keep the required global profile. Follow
[the FinDer profile procedure](docs/installation-and-operations.md#configure-finder-profiles)
for adding/removing entries, coverage order and configuration files.

Then configure which ShakeMap profile to use for each area. PyFinder tests the
selected FinDer solution's coordinates, which it also writes to `event.xml`,
against your ShakeMap coverage areas. These coordinates may differ from the
original earthquake alert. They are not matched against a country-code database.

A coverage file is WKT text describing the area's boundary: a WGS84
longitude/latitude `POLYGON` or `MULTIPOLYGON`. You can keep the packaged coverage
if it fits your workflow. To use your own area, put your file, for example
`my_coverage.wkt`, in `../pyfinder/pyfinder/extern/shakemap_regional_wkt/`. In the
`shakemap` section of [pyfinderconfig.py](../pyfinder/pyfinder/pyfinderconfig.py),
edit `regional-configurations` for the areas you intend to use. This ShakeMap
mapping must contain at least one entry; use this pattern for your own:

```text
"regional-configurations": {
    "my_service_area": {
        "wkt": "my_coverage.wkt",
        "configuration": "my_shakemap",
    },
},
```

Here `my_service_area` is your label, `my_coverage.wkt` is your boundary file, and
`my_shakemap` must match the profile directory you will create in step 5. Use your
own names; labels are arbitrary, and profile names are directory names rather
than paths. The area can cross Switzerland, Italy and Germany or contain separate
polygons. Two Swiss FinDer profiles can share one ShakeMap profile; an Italian
operator can independently choose a different profile. No country requires a
particular dataset or the installation of another region.

Register only boundary files you provide. Replace overlapping example entries
rather than adding a different profile over the same area. Overlapping areas
that name the same profile are allowed. Outside all areas, PyFinder uses global.
If a registered boundary file is unusable or matching areas name different
profiles, PyFinder logs a warning and uses global. There is no priority between
ShakeMap profiles.

Finish these coverage/configuration edits before building PyFinder in step 4.
The files are packaged in its image, so later changes require rebuilding and
replacing the PyFinder container. Your ShakeMap data/configuration files in step 5
are separate runtime files. If they reference an additional Python model package,
[install it in the ShakeMap image](docs/installation-and-operations.md#install-additional-shakemap-models)
before building that image. There is no generic custom-model installer.

## 4. Build the images, prepare global data and start ShakeMap

Build the two images from your configured checkouts. This installs the application
software inside Docker without starting continuous earthquake processing:

```sh
make build COMPONENT=pyfinder
make build COMPONENT=shakemap
```

ShakeMap needs two external global grids. The data helper can download the
supported files from USGS into this deployment checkout:

| File | Purpose |
| --- | --- |
| `runtime/shakemap/data/global/vs30/global_vs30.grd` | Ground conditions used by the global configuration |
| `runtime/shakemap/data/global/topo/topo_30sec.grd` | Elevation data for drawing maps |

These files are required even for a regional deployment: the installation test
uses the global configuration. Global is also used outside your registered areas,
and PyFinder can request it separately after certain regional configuration
failures. Your own regional datasets do not replace these global files.

First, inspect the paths and whether the files exist and are readable. Nothing is
downloaded or changed; missing files are normal on a new installation.

```sh
make data COMPONENT=shakemap DATA_ACTION=inspect
```

Next, download missing files. The helper checks downloaded files and reuses valid
existing copies. It stops if an existing file is invalid or unreadable and leaves
that file unchanged. Follow the reported correction before retrying. For offline
copies, use [the manual import instructions](docs/installation-and-operations.md#data-initialization-and-ownership).

```sh
make data COMPONENT=shakemap DATA_ACTION=provision
```

Verify that both files exactly match the versions expected by this project. This
reads the complete files and can take time. Continue when the report shows
`pinned_integrity_valid: true`; otherwise follow its `corrective_action` and repeat.

```sh
make data COMPONENT=shakemap DATA_ACTION=validate
```

Now prepare the runtime directories, check container access and run ShakeMap on
the supplied global test earthquake. This tests the installed service and its
result, not one of your events or regional configurations:

```sh
make finalize COMPONENT=shakemap
```

Success prints that the deployment is finalized and ready at its service URL.
**ShakeMap is now running**; no second start command is needed. If this command
fails, correct the reported phase and retry; the service may have stopped or
remain unavailable for calculations. Optional regional files may be supplied
later without preventing this global installation test from succeeding.

## 5. Install and test your ShakeMap profiles

For each regional profile you intend to use, provide these five native ShakeMap
configuration files and the datasets referenced by them. Use your own profile or
adapt a complete example from `../shakemap-docker/regional-configs/<seed>/`,
reviewing its models and file references. For the name used in step 3:

```text
runtime/shakemap/data/regional/my_shakemap/
├── gmpe_sets.conf
├── model.conf
├── modules.conf
├── products.conf
├── select.conf
├── assets/             # optional place for your datasets
└── layers/             # optional place for native selection polygons
```

All five `.conf` files are required; the extra folders are examples. Finalization
copies bundled profile directories only when absent, and does not complete or
merge an existing profile. Put complete files in place before testing; do not
edit them while a calculation may be reading them. UID/GID `1000:1000` must be
able to read the configuration and datasets.

The datasets needed depend on your configuration. Set paths visible **inside the
container**: host `runtime/shakemap/...` appears as
`/home/sysop/runtime/shakemap/...`.

| Configuration entry | What it refers to |
| --- | --- |
| `model.conf [data] vs30file` | Your intended VS30 grid |
| `products.conf [products][mapping][layers] topography` | The topography used for maps |
| `select.conf [layers] layer_dir` | Original native WKT polygons used to choose scientific models |
| `modules.conf` | Model classes and Python modules installed in the ShakeMap image |

For example, a grid at
`runtime/shakemap/data/regional/my_shakemap/assets/site_conditions.grd` must be
referenced as
`/home/sysop/runtime/shakemap/data/regional/my_shakemap/assets/site_conditions.grd`.
Use your actual filename. The native selection polygons are separate from the
FinDer and ShakeMap coverage boundaries in step 3. Helpers do not find regional
datasets or rewrite your paths; old `/home/shake/...` paths are not these mounts.
See the [file checklist](../shakemap-docker/docs/configuration.md#regional-profile-file-checklist)
for detailed native keys and examples.

Runtime configuration/data edits need no PyFinder rebuild. Additional model code
must be installed in the service image; after changing that image, rebuild and
finalize ShakeMap again. If your profile uses `GenericAmpFactors`, the current
service does not copy those files into its per-calculation profile. Placing them
under runtime is insufficient: that feature needs additional service support
before you can rely on the profile.

Check for missing files, bad references and unavailable model modules before
submitting a calculation. Replace the example profile and host URL/port:

```sh
shake-in-docker --url http://127.0.0.1:9010 check --configuration my_shakemap
```

Correct the findings for this profile and repeat. A result of `NO_KNOWN_BLOCKERS`
means the checks found no known missing prerequisite; it does not establish that
the profile can calculate correctly. Test it with representative native
`event.xml`, station-amplitude `event_dat.xml` and any required rupture/other
inputs.

A calculation ID is a name you choose for one calculation. `regional-test-001`
below is an example, not a reserved keyword or a value generated by the service.
Choose a name that has not been used on your installation to keep this test
separate from earlier results. Use exactly the same chosen name in `submit`,
`status` and `products`, changing all three examples if you choose another name.
Replace the input paths with the actual full **host** paths to your `event.xml`
and `event_dat.xml`; use your installed profile name and host service URL.

```sh
shake-in-docker --url http://127.0.0.1:9010 submit regional-test-001 \
  --configuration my_shakemap --overwrite false \
  --file /absolute/path/event.xml --file /absolute/path/event_dat.xml
shake-in-docker --url http://127.0.0.1:9010 status regional-test-001
```

Add `--file` for any other inputs. Save the returned `internal_sequence` and find
that number in the status response's `jobs` list. Repeat `status` until that job
is `SUCCESS` or `FAILED`. A successful result must also have
`job_completed=true` and `products_ready=true`. On failure, read the job's reported
error and its log paths before correcting and testing again.

For a successful job, inspect its products:

```sh
shake-in-docker --url http://127.0.0.1:9010 products regional-test-001
```

`current.internal_sequence` must match the submitted job; `current.manifest_state`
must be `complete`, with every `current.required_products` check passed. The
[calculation evidence guide](docs/verification.md#check-a-regional-calculation)
shows the exact fields and how to check the product inventory, provenance and
logs. Merely finding output files is insufficient. `--overwrite false` preserves
an earlier calculation in an archive if an ID is reused; the default `true`
discards it.

You can collect optional regional inputs while global calculations remain
available. Until your profile has passed its own test, do not treat the global
installation test or a listed profile name as proof that the region works.

## 6. Check PyFinder before starting live processing

The following checks use temporary PyFinder containers. Keep
`PYFINDER_SHAKEMAP_ENABLED=false` and the container name `pyfinder-docker`
**absent**; a stopped container still occupies the name. For an existing PyFinder
container, follow [the upgrade procedure](#upgrade-the-caller) to preserve its files first.

First, check the packages actually installed in the image. This check has network
access disabled and does not query providers or run FinDer:

```sh
make verify-image
```

Next, run a one-time connection check from the PyFinder image. It checks the
shared input directory and the ShakeMap address using temporary files and
read-only service requests. Choose a new absolute directory outside runtime for
its logs/results; its parent must exist, but the chosen directory must not:

```sh
make verify-caller EVIDENCE=/absolute/fresh/evidence-directory
```

Success prints `Finite installed caller checks passed`; its `summary.json` has
`"passed": true`. This confirms the configured address from inside the PyFinder
container. If it fails, read the terminal error and any saved report/logs. Correct
the reported problem, then repeat with a new evidence directory. Do not start
live PyFinder to test connectivity.

Wait for both checks to finish successfully, then review deployment diagnostics:

```sh
make check
```

Before live startup, this report still marks the absent PyFinder container and
disabled integration as blocked. Those entries are expected at this step; do not
start the application just to clear them. Unresolved service readiness, global
data or connection failures need correction before activation. Missing optional
regional inputs do not stop global setup, but remain limitations of those profiles.
Use [the before-activation table](docs/verification.md#before-activation) to decide
what needs action, including any existing queue or email configuration.

During live work, PyFinder attempts the selected regional profile first. After a
confirmed regional configuration failure it may submit one separate global
calculation. Both attempts are retained. ShakeMap itself never replaces your
requested profile with global, and a regional failure does not stop the service.

Host application tests are [optional developer checks](docs/verification.md#optional-developer-host-tests)
with extra host dependencies; they are not part of operator installation.

## 7. Start and operate PyFinder

After the preceding checks and queue/email review, set
`PYFINDER_SHAKEMAP_ENABLED=true` in `deployment.env`. The next command starts live
alerts and calculations, and may resume overdue queued work:

```sh
make start COMPONENT=pyfinder
make verify
```

`make verify` checks image identities, mounts and settings while both containers
are running. Use `make status` for container state and `make check` for diagnostic
actions. To resume an already-finalized installation, start ShakeMap first with
`make start COMPONENT=shakemap`, then start PyFinder.

Stop PyFinder before ShakeMap; these commands retain containers and runtime data:

```sh
make stop COMPONENT=pyfinder
make stop COMPONENT=shakemap
```

See [operations and logs](docs/installation-and-operations.md#logs-and-troubleshooting)
for troubleshooting, playback and scheduler reset. No restart supervisor is
installed. `make help` lists commands and the helper scripts accept `--help`.

## Upgrade the caller

Here, "caller" means the PyFinder container that submits jobs to ShakeMap. Follow
[the upgrade procedure](docs/installation-and-operations.md#upgrade-the-caller)
before replacing it. Preserve container-only files and mounted runtime, rebuild,
check installed packages and repeat the checks before activation. Cached builds
may retain older dependencies; restarting a container does not install changes.
Previously prepared calculations retain their selected profile, inputs and
replacement/archive choice. An upgrade does not require deleting the queue.
