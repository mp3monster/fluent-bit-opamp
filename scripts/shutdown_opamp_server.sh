#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8080}"

curl -sS -X POST "http://${HOST}:${PORT}/api/shutdown" \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
