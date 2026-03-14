#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

CONFIG_PATH="${REPO_ROOT}/tests/opamp.json"
FLUENTBIT_PATH="${REPO_ROOT}/tests/fluent-bit.yaml"
if [ ! -f "${CONFIG_PATH}" ]; then
  CONFIG_PATH="${REPO_ROOT}/consumer/opamp.json"
fi
if [ ! -f "${FLUENTBIT_PATH}" ]; then
  FLUENTBIT_PATH="${REPO_ROOT}/consumer/fluent-bit.yaml"
fi

export PYTHONPATH="${REPO_ROOT}/consumer/src"
export OPAMP_CONFIG_PATH="${CONFIG_PATH}"
python3 -m pip show httpx >/dev/null 2>&1 || python3 -m pip install -r "${REPO_ROOT}/consumer/requirements.txt"
python3 -m opamp_consumer.client --config-path "${CONFIG_PATH}" --fluentbit-config-path "${FLUENTBIT_PATH}" "$@"
