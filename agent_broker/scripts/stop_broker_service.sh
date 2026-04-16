#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${BROKER_RUNTIME_DIR:-${ROOT_DIR}/.broker}"
PID_FILE="${BROKER_PID_FILE:-${RUNTIME_DIR}/broker.pid}"
SHUTDOWN_TIMEOUT="${BROKER_SHUTDOWN_TIMEOUT_SECONDS:-30}"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "Broker PID file not found: ${PID_FILE}"
  echo "Broker may already be stopped."
  exit 0
fi

broker_pid="$(cat "${PID_FILE}")"
if [[ -z "${broker_pid}" ]]; then
  rm -f "${PID_FILE}"
  echo "Broker PID file was empty; cleared stale file."
  exit 0
fi

if ! kill -0 "${broker_pid}" 2>/dev/null; then
  rm -f "${PID_FILE}"
  echo "Broker process ${broker_pid} is not running; cleared stale PID file."
  exit 0
fi

echo "Requesting graceful broker shutdown (SIGTERM) for pid=${broker_pid} ..."
kill -TERM "${broker_pid}"

for ((elapsed=0; elapsed<SHUTDOWN_TIMEOUT; elapsed++)); do
  if ! kill -0 "${broker_pid}" 2>/dev/null; then
    rm -f "${PID_FILE}"
    echo "Broker stopped gracefully."
    exit 0
  fi
  sleep 1
done

echo "Broker is still running after ${SHUTDOWN_TIMEOUT}s."
echo "You can retry or force-stop manually (for example: kill -KILL ${broker_pid})."
exit 1
