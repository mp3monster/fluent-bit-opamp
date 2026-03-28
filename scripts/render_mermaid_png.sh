#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
NODE_BIN="${REPO_ROOT}/tools/node-v20.19.2-linux-x64/bin"
MMDC_BIN="${REPO_ROOT}/tools/mermaid/node_modules/.bin/mmdc"
PUPPETEER_CONFIG="${REPO_ROOT}/tools/mermaid/puppeteer-config.json"
PUPPETEER_CACHE_DIR="${REPO_ROOT}/tools/mermaid/.cache/puppeteer"
MERMAID_RUNTIME_LIB="${REPO_ROOT}/tools/mermaid-runtime/usr/lib/x86_64-linux-gnu:${REPO_ROOT}/tools/mermaid-runtime/lib/x86_64-linux-gnu"

if [[ ! -x "${NODE_BIN}/node" ]]; then
  echo "Missing Node runtime at ${NODE_BIN}. Install tooling first." >&2
  exit 1
fi

if [[ ! -x "${MMDC_BIN}" ]]; then
  echo "Missing Mermaid CLI at ${MMDC_BIN}. Install tooling first." >&2
  exit 1
fi

if [[ ! -f "${PUPPETEER_CONFIG}" ]]; then
  echo "Missing Puppeteer config at ${PUPPETEER_CONFIG}." >&2
  exit 1
fi

export PATH="${NODE_BIN}:${PATH}"
export PUPPETEER_CACHE_DIR
export LD_LIBRARY_PATH="${MERMAID_RUNTIME_LIB}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export TMPDIR=/tmp
export TMP=/tmp
export TEMP=/tmp

exec "${MMDC_BIN}" -p "${PUPPETEER_CONFIG}" "$@"
