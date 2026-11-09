#!/usr/bin/env bash
# Inspect the deployment without starting services or running calculations.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${VIRTUAL_ENV:-}" || "$(command -v python)" != "${VIRTUAL_ENV}/bin/python" ]]; then
    printf 'Activate the existing project environment: source %q\n' "${SCRIPT_DIR}/../../.venv/bin/activate" >&2
    echo "For missing host packages, see docs/installation-and-operations.md in pyfinder-deploy." >&2
    exit 2
fi
exec "${VIRTUAL_ENV}/bin/python" -B "${SCRIPT_DIR}/deployment.py" check "$@"
