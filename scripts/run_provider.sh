#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

export PYTHONPATH="${REPO_ROOT}/provider/src"
python3 -m pip show protobuf >/dev/null 2>&1 || python3 -m pip install -r "${REPO_ROOT}/provider/requirements.txt"
python3 -m opamp_provider.server "$@"
