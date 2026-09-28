#!/usr/bin/env bash
# Keep host tests in the existing project environment and the deployment tree.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${VIRTUAL_ENV:-}" || "$(command -v python)" != "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "Activate /Users/savas/my-codes/eew/pyfinder-dev/.venv before running deployment tests." >&2
    exit 2
fi
cd "${SCRIPT_DIR}/.."
exec "${VIRTUAL_ENV}/bin/python" -m unittest discover -s tests -v
