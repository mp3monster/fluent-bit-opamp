#!/usr/bin/env bash
set -euo pipefail

if pgrep -x fluent-bit >/dev/null 2>&1; then
  pkill -TERM -x fluent-bit
  echo "Sent SIGTERM to fluent-bit."
else
  echo "No fluent-bit process found."
fi
