#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
LOG_FILE="${LOG_DIR}/supervisor_fluentd.log"

if [[ -t 1 ]]; then
  printf '\033]0;%s\007' "OpAMP Supervisor (Fluentd)"
fi

if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

CONFIG_PATH="${REPO_ROOT}/consumer/opamp-fluentd.json"
FLUENTD_PATH="${REPO_ROOT}/consumer/fluentd.conf"
if [ ! -f "${CONFIG_PATH}" ]; then
  CONFIG_PATH="${REPO_ROOT}/tests/opamp.json"
fi
if [ ! -f "${CONFIG_PATH}" ]; then
  CONFIG_PATH="${REPO_ROOT}/config/opamp.json"
fi

export PYTHONPATH="${REPO_ROOT}/consumer/src"
export OPAMP_CONFIG_PATH="${CONFIG_PATH}"
echo "Using consumer config file: ${CONFIG_PATH}"
python3 -m pip show httpx >/dev/null 2>&1 || python3 -m pip install -r "${REPO_ROOT}/consumer/requirements.txt"
rm -f "${PWD}/OpAMPSupervisor.signal"
mkdir -p "${LOG_DIR}"
rm -f "${LOG_FILE}"
python3 -m opamp_consumer.fluentd_client --config-path "${CONFIG_PATH}" --fluentd-config-path "${FLUENTD_PATH}" "$@" 2>&1 | tee "${LOG_FILE}"
