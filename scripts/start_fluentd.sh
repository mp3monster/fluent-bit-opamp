#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FLUENTD_CONFIG_PATH="${REPO_ROOT}/consumer/fluentd.conf"
if [ ! -f "${FLUENTD_CONFIG_PATH}" ]; then
  echo "No fluentd config file found at consumer/fluentd.conf"
  exit 1
fi

if ! command -v fluentd >/dev/null 2>&1; then
  echo "fluentd command not found in PATH"
  exit 1
fi

echo "Starting fluentd with config: ${FLUENTD_CONFIG_PATH}"
exec fluentd -c "${FLUENTD_CONFIG_PATH}" "$@"
