#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
LOG_FILE="${LOG_DIR}/opamp_server.log"

if [[ -t 1 ]]; then
  printf '\033]0;%s\007' "OpAMP Server"
fi

if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

export PYTHONPATH="${REPO_ROOT}/provider/src"
python3 -m pip show protobuf >/dev/null 2>&1 || python3 -m pip install -r "${REPO_ROOT}/provider/requirements.txt"
mkdir -p "${LOG_DIR}"
rm -f "${LOG_FILE}"
python3 -m opamp_provider.server "$@" 2>&1 | tee "${LOG_FILE}"
