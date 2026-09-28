#!/usr/bin/env bash
# Delegate this responsibility to the shared literal-settings implementation.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${VIRTUAL_ENV:-}" || "$(command -v python)" != "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "Activate the existing project .venv before running deployment helpers." >&2
    exit 2
fi
exec "${VIRTUAL_ENV}/bin/python" "${SCRIPT_DIR}/deployment.py" setup "$@"
