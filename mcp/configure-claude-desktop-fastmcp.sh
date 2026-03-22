#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVER_SPEC="${REPO_ROOT}/provider/src/opamp_provider/mcptool/routes.py:mcpserver"
SERVER_NAME="OpAMP Server"
PROJECT_DIR="${REPO_ROOT}/provider"
PROVIDER_SRC_DIR="${REPO_ROOT}/provider/src"
OPAMP_SERVER_IP=""
USE_EDITABLE=true

usage() {
  cat <<'EOF'
Usage: ./mcp/configure-claude-desktop-fastmcp.sh [options]

Install the OpAMP MCP server into Claude Desktop using fastmcp CLI.

Options:
  --server-spec <value>   Server spec (default: provider/src/opamp_provider/mcptool/routes.py:mcpserver)
  --name <value>          Claude Desktop display name (default: OpAMP Server)
  --project <path>        Project directory for fastmcp --project and --with-editable
  --opamp-server-ip <ip>  OpAMP server IP (if omitted, prompts; default: localhost)
  --no-editable           Skip --with-editable
  -h, --help              Show this help
EOF
}

ensure_command() {
  command -v "$1" >/dev/null 2>&1
}

append_path_if_missing() {
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
  local runtime_path="${PATH}"
  local tools=(python3 uv fastmcp node npm)
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

install_python() {
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-spec)
      SERVER_SPEC="$2"
      shift 2
      ;;
    --name)
      SERVER_NAME="$2"
      shift 2
      ;;
    --project)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --opamp-server-ip)
      OPAMP_SERVER_IP="$2"
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

install_python
install_pip
install_uv
install_fastmcp
RUNTIME_PATH="$(build_runtime_path)"

if [[ -z "${OPAMP_SERVER_IP}" ]]; then
  read -r -p "Enter OpAMP server IP (default: localhost): " OPAMP_SERVER_IP
  OPAMP_SERVER_IP="${OPAMP_SERVER_IP:-localhost}"
fi
OPAMP_SERVER_URL="http://${OPAMP_SERVER_IP}:8000"
OPAMP_MCP_SSE_URL="${OPAMP_SERVER_URL}/sse"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project directory not found: ${PROJECT_DIR}" >&2
  exit 1
fi

CMD=(
  fastmcp install claude-desktop
  --name "${SERVER_NAME}"
  --project "${PROJECT_DIR}"
  --env "PYTHONPATH=${REPO_ROOT}:${PROVIDER_SRC_DIR}"
  --env "OPAMP_SERVER_IP=${OPAMP_SERVER_IP}"
  --env "OPAMP_SERVER_URL=${OPAMP_SERVER_URL}"
  --env "OPAMP_MCP_SSE_URL=${OPAMP_MCP_SSE_URL}"
  --env "PATH=${RUNTIME_PATH}"
)

if [[ "${USE_EDITABLE}" == true ]]; then
  CMD+=(--with-editable "${PROJECT_DIR}")
fi

CMD+=("${SERVER_SPEC}")

echo "Installing Claude Desktop MCP server via fastmcp..."
printf 'Command:'
for arg in "${CMD[@]}"; do
  printf ' %q' "${arg}"
done
printf '\n'

"${CMD[@]}"

echo "Claude Desktop configuration has been updated via fastmcp."
