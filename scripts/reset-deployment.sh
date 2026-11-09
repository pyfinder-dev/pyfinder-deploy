#!/usr/bin/env bash
# Clear only scheduler rows; the helper refuses a running or unknown caller.
set -euo pipefail
# Make exports COMPONENT even though reset has one fixed target. Refuse a
# selector here before Python can touch the scheduler database.
if [[ -n "${COMPONENT:-}" ]]; then
    echo "reset clears only PyFinder scheduled rows; omit COMPONENT." >&2
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${VIRTUAL_ENV:-}" || "$(command -v python)" != "${VIRTUAL_ENV}/bin/python" ]]; then
    printf 'Activate the existing project environment: source %q\n' "${SCRIPT_DIR}/../../.venv/bin/activate" >&2
    echo "For missing host packages, see docs/installation-and-operations.md in pyfinder-deploy." >&2
    exit 2
fi
exec "${VIRTUAL_ENV}/bin/python" -B "${SCRIPT_DIR}/deployment.py" reset "$@"
