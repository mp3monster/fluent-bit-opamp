#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT_DIR}/dist"
mkdir -p "${OUT}"
cd "${ROOT_DIR}/.."
zip -r "${OUT}/opamp-conversation-broker.zip" opamp_broker
