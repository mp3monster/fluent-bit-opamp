#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
SERVICE_MODE=0

if [[ "${1:-}" == "--service" ]]; then
  SERVICE_MODE=1
  shift
fi

if [[ $# -gt 0 ]]; then
  echo "Unknown argument(s): $*"
  echo "Usage: ${0##*/} [--service]"
  exit 1
fi

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export BROKER_CONFIG_PATH="${BROKER_CONFIG_PATH:-${ROOT_DIR}/opamp_broker/config/broker.example.json}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
pip install -r "${ROOT_DIR}/requirements.txt"

if [[ "${SERVICE_MODE}" -eq 0 ]]; then
  exec python -m opamp_broker.broker_app
fi

RUNTIME_DIR="${BROKER_RUNTIME_DIR:-${ROOT_DIR}/.broker}"
PID_FILE="${BROKER_PID_FILE:-${RUNTIME_DIR}/broker.pid}"
LOG_FILE="${BROKER_LOG_FILE:-${RUNTIME_DIR}/broker.log}"

mkdir -p "${RUNTIME_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  existing_pid="$(cat "${PID_FILE}")"
  if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "Broker already running (pid=${existing_pid})."
    echo "Log file: ${LOG_FILE}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

nohup python -m opamp_broker.broker_app >>"${LOG_FILE}" 2>&1 &
broker_pid=$!
echo "${broker_pid}" >"${PID_FILE}"

sleep 1
if kill -0 "${broker_pid}" 2>/dev/null; then
  echo "Broker started (pid=${broker_pid})."
  echo "PID file: ${PID_FILE}"
  echo "Log file: ${LOG_FILE}"
  exit 0
fi

rm -f "${PID_FILE}"
echo "Broker failed to start. Check log file: ${LOG_FILE}"
exit 1
