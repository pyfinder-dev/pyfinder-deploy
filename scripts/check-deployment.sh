#!/usr/bin/env bash
# Inspect the deployment without starting services or running calculations.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${VIRTUAL_ENV:-}" || "$(command -v python)" != "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "Activate the existing project .venv before checking deployment." >&2
    exit 2
fi
exec "${VIRTUAL_ENV}/bin/python" -B "${SCRIPT_DIR}/deployment.py" check "$@"
