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

# Supports these MCP client targets:
# - Claude Desktop via `mcp-remote` SSE endpoint entry in `claude_desktop_config.json`
# - ChatGPT/Codex CLI via `codex mcp add`
# - VS Code by writing a `servers` entry in `.vscode/mcp.json`
#
# Default server names intentionally differ by client convention:
# - ChatGPT/Codex: `opamp-server` (kebab-case, CLI-friendly, and backward-compatible)
# - VS Code: `opampServer` (camelCase, aligned with VS Code MCP naming guidance)
# Override with `--chatgpt-name`/`--claude-name`/`--vscode-name` as needed.
#
# Target a specific client with `--clients`, for example:
# - `--clients claude`
# - `--clients chatgpt`
# - `--clients vscode`
# - `--clients claude,vscode`

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CHATGPT_SERVER_NAME="opamp-server" # Kebab-case keeps CLI compatibility with prior script defaults.
CLAUDE_SERVER_NAME="OpAMP Server"
VSCODE_SERVER_NAME="opampServer" # CamelCase follows VS Code MCP server naming guidance.
SERVER_SPEC="${REPO_ROOT}/provider/src/opamp_provider/mcptool/routes.py:mcpserver"
PROJECT_DIR="${REPO_ROOT}/provider"
PROVIDER_SRC_DIR="${REPO_ROOT}/provider/src"
SHARED_SRC_DIR="${REPO_ROOT}/shared"
VSCODE_CONFIG_PATH="${REPO_ROOT}/.vscode/mcp.json"
CLAUDE_CONFIG_PATH=""
OPAMP_SERVER_IP=""
OPAMP_SERVER_PORT="8080"
USE_EDITABLE=true
CLIENTS="claude,chatgpt,vscode"
INSTALL_CLAUDE=false
INSTALL_CHATGPT=false
INSTALL_VSCODE=false
NEED_LOCAL_SOURCE_PATHS=false
PYTHONPATH_VALUE=""
RUNTIME_PATH="${PATH}"
CLAUDE_REMOTE_COMMAND=""
CLAUDE_REMOTE_ARGS_JSON=""

usage() {
  cat <<'EOF'
Usage: ./mcp/configure-mcp-clients-fastmcp.sh [options]

Configure the OpAMP MCP server for Claude Desktop, ChatGPT (Codex CLI), and VS Code.

Options:
  --chatgpt-name <value>  ChatGPT/Codex MCP server name (default: opamp-server)
  --server-name <value>   Alias of --chatgpt-name (compatibility)
  --claude-name <value>   Claude Desktop display name (default: OpAMP Server)
  --vscode-name <value>   VS Code server name in mcp.json (default: opampServer)
  --vscode-config <path>  VS Code mcp.json path (default: .vscode/mcp.json in repo)
  --claude-config <path>  Claude Desktop config path (default: OS-specific user config path)
  --clients <list>        Comma-separated targets: claude,chatgpt,vscode
                          (default: claude,chatgpt,vscode)
                          Examples: --clients claude | --clients chatgpt |
                                    --clients vscode | --clients claude,vscode
  --server-spec <value>   Server spec (default: provider/src/opamp_provider/mcptool/routes.py:mcpserver)
  --project <path>        Project directory for uv --project/--with-editable
  --opamp-server-ip <ip>  OpAMP server IP (if omitted, prompts; default: localhost)
  --opamp-server-port <n> OpAMP server port used for URL env vars (default: 8080)
  --no-editable           Skip --with-editable
  -h, --help              Show this help
EOF
}

ensure_command() {
  # Returns success when the supplied executable is available on PATH.
  command -v "$1" >/dev/null 2>&1
}

require_option_value() {
  # Ensures an option that requires a value has a following argument.
  local option_name="$1"
  local option_value="${2:-}"
  if [[ -z "${option_value}" || "${option_value}" == --* ]]; then
    echo "Missing value for ${option_name}" >&2
    usage
    exit 1
  fi
}

trim() {
  # Trims leading and trailing whitespace.
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

set_install_targets() {
  # Parses --clients and enables requested targets.
  local requested="$1"
  local target=""
  INSTALL_CLAUDE=false
  INSTALL_CHATGPT=false
  INSTALL_VSCODE=false

  IFS=',' read -r -a targets <<< "${requested}"
  for target in "${targets[@]}"; do
    target="$(trim "${target}" | tr '[:upper:]' '[:lower:]')"
    case "${target}" in
      claude)
        INSTALL_CLAUDE=true
        ;;
      chatgpt|codex)
        INSTALL_CHATGPT=true
        ;;
      vscode|vs-code|vs_code|vs)
        INSTALL_VSCODE=true
        ;;
      "")
        ;;
      *)
        echo "Unknown client target: ${target}" >&2
        echo "Expected one or more of: claude, chatgpt, vscode" >&2
        exit 1
        ;;
    esac
  done

  if [[ "${INSTALL_CLAUDE}" != true && "${INSTALL_CHATGPT}" != true && "${INSTALL_VSCODE}" != true ]]; then
    echo "No valid client targets selected. Use --clients claude,chatgpt,vscode." >&2
    exit 1
  fi
}

append_path_if_missing() {
  # Appends a directory to PATH only when it is non-empty and not already present.
  local current_path="$1"
  local dir_to_add="$2"
  if [[ -z "${dir_to_add}" ]]; then
    printf '%s' "${current_path}"
    return
  fi
  case ":${current_path}:" in
    *":${dir_to_add}:"*) printf '%s' "${current_path}" ;;
    *) printf '%s' "${current_path}:${dir_to_add}" ;;
  esac
}

build_runtime_path() {
  # Builds a PATH value that includes locations for required runtime tools.
  local runtime_path="${PATH}"
  local tools=(python3 uv fastmcp codex node npm)
  local tool_path=""
  local tool_dir=""
  for tool in "${tools[@]}"; do
    if tool_path="$(command -v "${tool}" 2>/dev/null)"; then
      tool_dir="$(dirname "${tool_path}")"
      runtime_path="$(append_path_if_missing "${runtime_path}" "${tool_dir}")"
    fi
  done
  printf '%s' "${runtime_path}"
}

detect_local_source_paths_needed() {
  # Determines whether local repo paths are required for opamp_provider/shared imports.
  local missing_modules=""
  local probe_dir="/tmp"
  if [[ ! -d "${probe_dir}" ]]; then
    probe_dir="/"
  fi
  missing_modules="$(
    cd "${probe_dir}" && python3 - <<'PY'
import importlib.util

required = ("opamp_provider", "shared")
missing = [name for name in required if importlib.util.find_spec(name) is None]
print(",".join(missing))
PY
  )"
  missing_modules="$(trim "${missing_modules}")"
  if [[ -n "${missing_modules}" ]]; then
    NEED_LOCAL_SOURCE_PATHS=true
    echo "Detected missing Python modules (${missing_modules}); using local source paths."
  else
    NEED_LOCAL_SOURCE_PATHS=false
    echo "Detected globally importable opamp_provider/shared modules; local source paths are optional."
  fi
}

build_pythonpath_value() {
  # Builds PYTHONPATH value, adding local repo/provider paths only when required.
  local result="${PYTHONPATH:-}"
  if [[ "${NEED_LOCAL_SOURCE_PATHS}" == true ]]; then
    result="$(append_path_if_missing "${result}" "${REPO_ROOT}")"
    result="$(append_path_if_missing "${result}" "${PROVIDER_SRC_DIR}")"
    result="$(append_path_if_missing "${result}" "${SHARED_SRC_DIR}")"
  fi
  PYTHONPATH_VALUE="${result}"
}

resolve_claude_config_path() {
  # Resolves Claude Desktop config path. Allows explicit override.
  if [[ -n "${CLAUDE_CONFIG_PATH}" ]]; then
    return 0
  fi
  if [[ "${OSTYPE:-}" == darwin* ]]; then
    CLAUDE_CONFIG_PATH="${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
  else
    local xdg_base="${XDG_CONFIG_HOME:-${HOME}/.config}"
    CLAUDE_CONFIG_PATH="${xdg_base}/Claude/claude_desktop_config.json"
  fi
}

resolve_claude_remote_launch() {
  # Resolves remote MCP launcher for Claude Desktop.
  # Preference order:
  # 1) direct mcp-remote binary
  # 2) npx -y mcp-remote
  local mcp_remote_path=""
  local npx_path=""
  if mcp_remote_path="$(command -v mcp-remote 2>/dev/null)"; then
    CLAUDE_REMOTE_COMMAND="${mcp_remote_path}"
    CLAUDE_REMOTE_ARGS_JSON="[\"${OPAMP_MCP_SSE_URL}\"]"
    return 0
  fi
  if npx_path="$(command -v npx 2>/dev/null)"; then
    CLAUDE_REMOTE_COMMAND="${npx_path}"
    CLAUDE_REMOTE_ARGS_JSON="[\"-y\",\"mcp-remote\",\"${OPAMP_MCP_SSE_URL}\"]"
    return 0
  fi
  echo "Neither 'mcp-remote' nor 'npx' was found on PATH." >&2
  echo "Install one of them before configuring Claude Desktop MCP." >&2
  exit 1
}

remove_legacy_codex_servers() {
  # Removes known legacy OpAMP server names from Codex MCP config while preserving active name.
  local keep_name="$1"
  local legacy_name=""
  for legacy_name in "OpAMP Server" "opamp-server" "opampServer"; do
    if [[ "${legacy_name,,}" == "${keep_name,,}" ]]; then
      continue
    fi
    if codex mcp get "${legacy_name}" >/dev/null 2>&1; then
      echo "Removing legacy ChatGPT/Codex MCP server '${legacy_name}'..."
      codex mcp remove "${legacy_name}" >/dev/null
    fi
  done
}

install_python() {
  # Ensures python3 is available, attempting package-manager install when absent.
  if ensure_command python3; then
    return 0
  fi
  echo "python3 not found. Attempting install..."
  if ensure_command brew; then
    brew install python || true
  elif ensure_command apt-get; then
    sudo apt-get update || true
    sudo apt-get install -y python3 python3-pip || true
  elif ensure_command dnf; then
    sudo dnf install -y python3 python3-pip || true
  elif ensure_command yum; then
    sudo yum install -y python3 python3-pip || true
  elif ensure_command pacman; then
    sudo pacman -Sy --noconfirm python python-pip || true
  fi
  if ! ensure_command python3; then
    echo "python3 is required. Install Python 3.10+ and re-run." >&2
    exit 1
  fi
}

install_pip() {
  # Ensures pip is available for python3.
  if python3 -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  echo "pip not found. Attempting bootstrap..."
  python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
  if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "pip is required. Install pip and re-run." >&2
    exit 1
  fi
}

install_uv() {
  # Ensures uv is available, first via pip then package managers.
  if ensure_command uv; then
    return 0
  fi
  echo "uv not found. Attempting install..."
  python3 -m pip install --upgrade uv >/dev/null 2>&1 || true
  if ! ensure_command uv; then
    if ensure_command brew; then
      brew install uv || true
    elif ensure_command apt-get; then
      sudo apt-get install -y uv || true
    elif ensure_command dnf; then
      sudo dnf install -y uv || true
    elif ensure_command yum; then
      sudo yum install -y uv || true
    elif ensure_command pacman; then
      sudo pacman -Sy --noconfirm uv || true
    fi
  fi
  if ! ensure_command uv; then
    echo "uv is required. Install uv and re-run." >&2
    exit 1
  fi
}

install_fastmcp() {
  # Ensures fastmcp CLI is available.
  if ensure_command fastmcp; then
    return 0
  fi
  echo "fastmcp not found. Installing with pip..."
  python3 -m pip install --upgrade fastmcp >/dev/null 2>&1 || true
  if ! ensure_command fastmcp; then
    echo "fastmcp install failed. Run: python3 -m pip install --upgrade fastmcp" >&2
    exit 1
  fi
}

install_claude_target() {
  # Writes Claude Desktop MCP config using mcp-remote/npx remote transport launch.
  if ! ensure_command python3; then
    echo "python3 is required to write Claude Desktop config JSON. Install Python 3 and re-run." >&2
    exit 1
  fi
  resolve_claude_config_path
  resolve_claude_remote_launch

  mkdir -p "$(dirname "${CLAUDE_CONFIG_PATH}")"

  python3 - "${CLAUDE_CONFIG_PATH}" "${CLAUDE_SERVER_NAME}" "${CLAUDE_REMOTE_COMMAND}" "${CLAUDE_REMOTE_ARGS_JSON}" "${OPAMP_SERVER_IP}" "${OPAMP_SERVER_URL}" "${OPAMP_MCP_SSE_URL}" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
server_name = sys.argv[2]
remote_command = sys.argv[3]
remote_args = json.loads(sys.argv[4])
server_ip = sys.argv[5]
server_url = sys.argv[6]
sse_url = sys.argv[7]

if config_path.exists():
    existing_text = config_path.read_text(encoding="utf-8").strip()
    document = json.loads(existing_text) if existing_text else {}
else:
    document = {}

if not isinstance(document, dict):
    raise SystemExit(f"Invalid Claude Desktop config format in {config_path}")

mcp_servers = document.get("mcpServers")
if not isinstance(mcp_servers, dict):
    mcp_servers = {}
document["mcpServers"] = mcp_servers

legacy_names = ("OpAMP Server", "opamp-server", "opampServer")
keep_lower = server_name.lower()
for legacy_name in legacy_names:
    if legacy_name.lower() == keep_lower:
        continue
    mcp_servers.pop(legacy_name, None)

mcp_servers[server_name] = {
    "command": remote_command,
    "args": remote_args,
    "env": {
        "OPAMP_SERVER_IP": server_ip,
        "OPAMP_SERVER_URL": server_url,
        "OPAMP_MCP_SSE_URL": sse_url,
    },
}

config_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
PY

  echo "Claude Desktop configuration has been updated at ${CLAUDE_CONFIG_PATH} (${CLAUDE_REMOTE_COMMAND} -> ${OPAMP_MCP_SSE_URL})."
}

install_chatgpt_target() {
  # Registers server in Codex CLI (shared with ChatGPT MCP usage where supported).
  local cmd=(
    codex mcp add "${CHATGPT_SERVER_NAME}"
    --env "OPAMP_SERVER_IP=${OPAMP_SERVER_IP}"
    --env "OPAMP_SERVER_URL=${OPAMP_SERVER_URL}"
    --env "OPAMP_MCP_SSE_URL=${OPAMP_MCP_SSE_URL}"
    --
    uv run
    --project "${PROJECT_DIR}"
    --with fastmcp
  )
  if [[ -n "${PYTHONPATH_VALUE}" ]]; then
    cmd+=(--env "PYTHONPATH=${PYTHONPATH_VALUE}")
  fi
  if [[ -n "${RUNTIME_PATH}" ]]; then
    cmd+=(--env "PATH=${RUNTIME_PATH}")
  fi

  if [[ "${USE_EDITABLE}" == true ]]; then
    cmd+=(--with-editable "${PROJECT_DIR}")
    if [[ "${NEED_LOCAL_SOURCE_PATHS}" == true ]]; then
      cmd+=(--with-editable "${REPO_ROOT}")
    fi
  fi

  cmd+=(fastmcp run "${SERVER_SPEC}")

  if codex mcp get "${CHATGPT_SERVER_NAME}" >/dev/null 2>&1; then
    echo "Existing ChatGPT/Codex MCP server '${CHATGPT_SERVER_NAME}' found. Replacing..."
    codex mcp remove "${CHATGPT_SERVER_NAME}" >/dev/null
  fi
  remove_legacy_codex_servers "${CHATGPT_SERVER_NAME}"

  echo "Registering MCP server in ChatGPT/Codex CLI..."
  printf 'Command:'
  for arg in "${cmd[@]}"; do
    printf ' %q' "${arg}"
  done
  printf '\n'

  "${cmd[@]}"
  echo "ChatGPT/Codex MCP server '${CHATGPT_SERVER_NAME}' has been configured."
}

install_vscode_target() {
  # Merges generated FastMCP stdio definition into VS Code mcp.json ("servers" schema).
  local mcp_json_cmd=(
    fastmcp install mcp-json
    --name "${VSCODE_SERVER_NAME}"
    --project "${PROJECT_DIR}"
    --env "OPAMP_SERVER_IP=${OPAMP_SERVER_IP}"
    --env "OPAMP_SERVER_URL=${OPAMP_SERVER_URL}"
    --env "OPAMP_MCP_SSE_URL=${OPAMP_MCP_SSE_URL}"
  )
  if [[ -n "${PYTHONPATH_VALUE}" ]]; then
    mcp_json_cmd+=(--env "PYTHONPATH=${PYTHONPATH_VALUE}")
  fi
  if [[ -n "${RUNTIME_PATH}" ]]; then
    mcp_json_cmd+=(--env "PATH=${RUNTIME_PATH}")
  fi
  local generated_json=""

  if [[ "${USE_EDITABLE}" == true ]]; then
    mcp_json_cmd+=(--with-editable "${PROJECT_DIR}")
    if [[ "${NEED_LOCAL_SOURCE_PATHS}" == true ]]; then
      mcp_json_cmd+=(--with-editable "${REPO_ROOT}")
    fi
  fi
  mcp_json_cmd+=("${SERVER_SPEC}")
  generated_json="$("${mcp_json_cmd[@]}")"

  mkdir -p "$(dirname "${VSCODE_CONFIG_PATH}")"

  printf '%s' "${generated_json}" | python3 - "${VSCODE_CONFIG_PATH}" "${VSCODE_SERVER_NAME}" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
server_name = sys.argv[2]
snippet = json.loads(sys.stdin.read())
server_config = snippet.get(server_name)
if server_config is None and snippet:
    server_config = next(iter(snippet.values()))
if server_config is None:
    raise SystemExit("Unable to parse generated MCP JSON for VS Code")
server_config = dict(server_config)
server_config.setdefault("type", "stdio")

if config_path.exists():
    existing_text = config_path.read_text(encoding="utf-8").strip()
    document = json.loads(existing_text) if existing_text else {}
else:
    document = {}

if not isinstance(document, dict):
    raise SystemExit(f"Invalid VS Code MCP config format in {config_path}")

servers = document.get("servers")
if not isinstance(servers, dict):
    servers = {}
document["servers"] = servers
legacy_names = ("OpAMP Server", "opamp-server", "opampServer")
keep_lower = server_name.lower()
for legacy_name in legacy_names:
    if legacy_name.lower() == keep_lower:
        continue
    servers.pop(legacy_name, None)
servers[server_name] = server_config

config_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
PY

  echo "VS Code MCP configuration updated at ${VSCODE_CONFIG_PATH}."
}

ensure_codex() {
  # Ensures codex CLI is available before registering the MCP server.
  if ensure_command codex; then
    return 0
  fi
  echo "codex CLI is required but not on PATH. Install Codex CLI and re-run." >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chatgpt-name|--server-name|--name)
      require_option_value "$1" "${2:-}"
      CHATGPT_SERVER_NAME="$2"
      shift 2
      ;;
    --claude-name)
      require_option_value "$1" "${2:-}"
      CLAUDE_SERVER_NAME="$2"
      shift 2
      ;;
    --vscode-name)
      require_option_value "$1" "${2:-}"
      VSCODE_SERVER_NAME="$2"
      shift 2
      ;;
    --vscode-config)
      require_option_value "$1" "${2:-}"
      VSCODE_CONFIG_PATH="$2"
      shift 2
      ;;
    --claude-config)
      require_option_value "$1" "${2:-}"
      CLAUDE_CONFIG_PATH="$2"
      shift 2
      ;;
    --clients)
      require_option_value "$1" "${2:-}"
      CLIENTS="$2"
      shift 2
      ;;
    --server-spec)
      require_option_value "$1" "${2:-}"
      SERVER_SPEC="$2"
      shift 2
      ;;
    --project)
      require_option_value "$1" "${2:-}"
      PROJECT_DIR="$2"
      shift 2
      ;;
    --opamp-server-ip)
      require_option_value "$1" "${2:-}"
      OPAMP_SERVER_IP="$2"
      shift 2
      ;;
    --opamp-server-port)
      require_option_value "$1" "${2:-}"
      OPAMP_SERVER_PORT="$2"
      shift 2
      ;;
    --no-editable)
      USE_EDITABLE=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

set_install_targets "${CLIENTS}"

if [[ -z "${OPAMP_SERVER_IP}" ]]; then
  read -r -p "Enter OpAMP server IP (default: localhost): " OPAMP_SERVER_IP
  OPAMP_SERVER_IP="${OPAMP_SERVER_IP:-localhost}"
fi
OPAMP_SERVER_URL="http://${OPAMP_SERVER_IP}:${OPAMP_SERVER_PORT}"
OPAMP_MCP_SSE_URL="${OPAMP_SERVER_URL}/sse"

if [[ "${INSTALL_CHATGPT}" == true || "${INSTALL_VSCODE}" == true ]]; then
  install_python
  install_pip
  install_uv
  detect_local_source_paths_needed
  build_pythonpath_value
  RUNTIME_PATH="$(build_runtime_path)"
else
  NEED_LOCAL_SOURCE_PATHS=false
  PYTHONPATH_VALUE=""
  RUNTIME_PATH="${PATH}"
fi

if [[ "${INSTALL_VSCODE}" == true ]]; then
  install_fastmcp
fi

if [[ "${INSTALL_CHATGPT}" == true || "${INSTALL_VSCODE}" == true ]] && [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project directory not found: ${PROJECT_DIR}" >&2
  exit 1
fi

if [[ "${INSTALL_CLAUDE}" == true ]]; then
  install_claude_target
fi

if [[ "${INSTALL_CHATGPT}" == true ]]; then
  ensure_codex
  install_chatgpt_target
fi

if [[ "${INSTALL_VSCODE}" == true ]]; then
  install_vscode_target
fi

echo "Completed MCP client installation for targets: ${CLIENTS}."
