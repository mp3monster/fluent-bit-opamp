#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
LOG_FILE="${LOG_DIR}/opamp_server.log"
ENABLE_HTTPS=0
SERVER_ARGS=()
CONFIG_PATH_OVERRIDE=""
ALL_ARGS=("$@")
ARG_INDEX=0
while [[ "${ARG_INDEX}" -lt "${#ALL_ARGS[@]}" ]]; do
  arg="${ALL_ARGS[${ARG_INDEX}]}"
  if [[ "${arg}" == "--https" ]]; then
    ENABLE_HTTPS=1
    ARG_INDEX=$((ARG_INDEX + 1))
    continue
  fi
  if [[ "${arg}" == "--config-path" ]]; then
    SERVER_ARGS+=("${arg}")
    ARG_INDEX=$((ARG_INDEX + 1))
    if [[ "${ARG_INDEX}" -lt "${#ALL_ARGS[@]}" ]]; then
      next_arg="${ALL_ARGS[${ARG_INDEX}]}"
      CONFIG_PATH_OVERRIDE="${next_arg}"
      SERVER_ARGS+=("${next_arg}")
    fi
    ARG_INDEX=$((ARG_INDEX + 1))
    continue
  fi
  if [[ "${arg}" == --config-path=* ]]; then
    CONFIG_PATH_OVERRIDE="${arg#--config-path=}"
  fi
  SERVER_ARGS+=("${arg}")
  ARG_INDEX=$((ARG_INDEX + 1))
done

if [[ -t 1 ]]; then
  printf '\033]0;%s\007' "OpAMP Server"
fi

if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

PROVIDER_CONFIG_PATH="${CONFIG_PATH_OVERRIDE:-${OPAMP_CONFIG_PATH:-${REPO_ROOT}/config/opamp.json}}"
export OPAMP_CONFIG_PATH="${PROVIDER_CONFIG_PATH}"
echo "Using provider config file: ${PROVIDER_CONFIG_PATH}"
export PYTHONPATH="${REPO_ROOT}/provider/src"
python3 -m pip show protobuf >/dev/null 2>&1 || python3 -m pip install -r "${REPO_ROOT}/provider/requirements.txt"

if [[ "${ENABLE_HTTPS}" -eq 1 ]]; then
  CERT_DIR="${REPO_ROOT}/certs"
  CERT_FILE="${CERT_DIR}/provider-server.pem"
  KEY_FILE="${CERT_DIR}/provider-server-key.pem"
  python3 "${REPO_ROOT}/scripts/generate_self_signed_tls_cert.py" \
    --force \
    --cert-file "${CERT_FILE}" \
    --key-file "${KEY_FILE}" \
    --common-name "localhost" \
    --dns-name "localhost" \
    --ip-address "127.0.0.1" \
    --days 365
  python3 "${REPO_ROOT}/scripts/ensure_provider_tls_config.py" \
    --config-file "${PROVIDER_CONFIG_PATH}" \
    --cert-file "${CERT_FILE}" \
    --key-file "${KEY_FILE}" \
    --trust-anchor-mode none
fi

mkdir -p "${LOG_DIR}"
rm -f "${LOG_FILE}"
python3 -m opamp_provider.server "${SERVER_ARGS[@]}" 2>&1 | tee "${LOG_FILE}"
