#!/usr/bin/env bash
# Copyright 2026 mp3monster.org
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Compatibility wrapper.
# This script preserves legacy semantics where --name maps to the ChatGPT/Codex MCP server name.
# It delegates execution to configure-mcp-clients-fastmcp.sh.
# Supported clients (via canonical script): Claude Desktop, ChatGPT/Codex, VS Code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_SCRIPT="${SCRIPT_DIR}/configure-mcp-clients-fastmcp.sh"

if [[ ! -f "${CANONICAL_SCRIPT}" ]]; then
  echo "Canonical script not found: ${CANONICAL_SCRIPT}" >&2
  exit 1
fi

FORWARDED_ARGS=()
HAS_CLIENTS_FLAG=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name|--server-name)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 1
      fi
      FORWARDED_ARGS+=(--chatgpt-name "$2")
      shift 2
      ;;
    --clients)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --clients" >&2
        exit 1
      fi
      HAS_CLIENTS_FLAG=true
      FORWARDED_ARGS+=("$1" "$2")
      shift 2
      ;;
    *)
      FORWARDED_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "${HAS_CLIENTS_FLAG}" != true ]]; then
  FORWARDED_ARGS+=(--clients "chatgpt")
fi

exec "${CANONICAL_SCRIPT}" "${FORWARDED_ARGS[@]}"
