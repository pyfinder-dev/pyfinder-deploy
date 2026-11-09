#!/usr/bin/env bash
# Run only the finite installed caller probe in the existing project environment.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ENVIRONMENT="$(cd "${SCRIPT_DIR}/../.." && pwd)/.venv"
if [[ "${VIRTUAL_ENV:-}" != "${PROJECT_ENVIRONMENT}" || "$(command -v python)" != "${PROJECT_ENVIRONMENT}/bin/python" ]]; then
    printf 'Activate the existing project environment: source %q\n' "${SCRIPT_DIR}/../../.venv/bin/activate" >&2
    echo "For missing host packages, see docs/installation-and-operations.md in pyfinder-deploy." >&2
    exit 2
fi
exec "${PROJECT_ENVIRONMENT}/bin/python" "${SCRIPT_DIR}/verify_caller_boundary.py" "$@"
