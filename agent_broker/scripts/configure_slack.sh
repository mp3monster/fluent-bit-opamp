#!/usr/bin/env bash
set -euo pipefail

# Generate Slack app manifest + broker env scaffolding for opamp_broker.
# This automates local file prep and token injection. Slack app creation and
# app-level token generation are still done in the Slack UI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${ROOT_DIR}/.env"
MANIFEST_FILE="${ROOT_DIR}/opamp_broker/config/slack_app_manifest.yaml"
APP_NAME="OpAMP Conversation Broker"
SLASH_COMMAND="/opamp"
NON_INTERACTIVE=false

SLACK_BOT_TOKEN="${SLACK_BOT_TOKEN:-}"
SLACK_SIGNING_SECRET="${SLACK_SIGNING_SECRET:-}"
SLACK_APP_TOKEN="${SLACK_APP_TOKEN:-}"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --env-file <path>         Target env file (default: ${ROOT_DIR}/.env)
  --manifest-file <path>    Slack manifest output path (default: ${MANIFEST_FILE})
  --app-name <name>         Slack app display name (default: ${APP_NAME})
  --command </name>         Slash command name (default: ${SLASH_COMMAND})
  --bot-token <token>       Set SLACK_BOT_TOKEN in env file
  --signing-secret <value>  Set SLACK_SIGNING_SECRET in env file
  --app-token <token>       Set SLACK_APP_TOKEN in env file
  --non-interactive         Do not prompt for missing values
  -h, --help                Show this help
EOF
}

set_env_var() {
  local file="$1"
  local key="$2"
  local value="$3"
  local escaped
  escaped="$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')"
  if grep -qE "^${key}=" "$file"; then
    sed -i -E "s|^${key}=.*$|${key}=${escaped}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

get_env_var() {
  local file="$1"
  local key="$2"
  if [[ ! -f "${file}" ]]; then
    printf ''
    return 0
  fi
  awk -F= -v key="${key}" '
    /^[[:space:]]*#/ { next }
    NF < 2 { next }
    $1 == key {
      $1=""
      sub(/^=/, "", $0)
      print $0
      exit
    }
  ' "${file}"
}

mask_secret() {
  local value="$1"
  local len="${#value}"
  if [[ -z "${value}" ]]; then
    printf '<empty>'
    return 0
  fi
  if (( len <= 8 )); then
    printf '%*s' "${len}" '' | tr ' ' '*'
    return 0
  fi
  printf '%s...%s' "${value:0:4}" "${value:len-4:4}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --manifest-file)
      MANIFEST_FILE="$2"
      shift 2
      ;;
    --app-name)
      APP_NAME="$2"
      shift 2
      ;;
    --command)
      SLASH_COMMAND="$2"
      shift 2
      ;;
    --bot-token)
      SLACK_BOT_TOKEN="$2"
      shift 2
      ;;
    --signing-secret)
      SLACK_SIGNING_SECRET="$2"
      shift 2
      ;;
    --app-token)
      SLACK_APP_TOKEN="$2"
      shift 2
      ;;
    --non-interactive)
      NON_INTERACTIVE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${SLASH_COMMAND}" != /* ]]; then
  echo "Slash command must start with '/': ${SLASH_COMMAND}" >&2
  exit 1
fi

mkdir -p "$(dirname "${ENV_FILE}")"
mkdir -p "$(dirname "${MANIFEST_FILE}")"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ENV_FILE}"
fi

EXISTING_SLACK_BOT_TOKEN="$(get_env_var "${ENV_FILE}" "SLACK_BOT_TOKEN")"
EXISTING_SLACK_SIGNING_SECRET="$(get_env_var "${ENV_FILE}" "SLACK_SIGNING_SECRET")"
EXISTING_SLACK_APP_TOKEN="$(get_env_var "${ENV_FILE}" "SLACK_APP_TOKEN")"

echo
echo "Current .env Slack values:"
echo "- SLACK_BOT_TOKEN: $(mask_secret "${EXISTING_SLACK_BOT_TOKEN}")"
echo "- SLACK_SIGNING_SECRET: $(mask_secret "${EXISTING_SLACK_SIGNING_SECRET}")"
echo "- SLACK_APP_TOKEN: $(mask_secret "${EXISTING_SLACK_APP_TOKEN}")"

if [[ -z "${SLACK_BOT_TOKEN}" ]]; then
  SLACK_BOT_TOKEN="${EXISTING_SLACK_BOT_TOKEN}"
fi
if [[ -z "${SLACK_SIGNING_SECRET}" ]]; then
  SLACK_SIGNING_SECRET="${EXISTING_SLACK_SIGNING_SECRET}"
fi
if [[ -z "${SLACK_APP_TOKEN}" ]]; then
  SLACK_APP_TOKEN="${EXISTING_SLACK_APP_TOKEN}"
fi

if [[ "${NON_INTERACTIVE}" == false ]]; then
  if [[ -n "${EXISTING_SLACK_BOT_TOKEN}" ]]; then
    read -r -p "SLACK_BOT_TOKEN (press Enter to keep existing): " _prompt_bot_token
    if [[ -n "${_prompt_bot_token}" ]]; then
      SLACK_BOT_TOKEN="${_prompt_bot_token}"
    fi
  elif [[ -z "${SLACK_BOT_TOKEN}" ]]; then
    read -r -p "SLACK_BOT_TOKEN (xoxb-..., optional now): " SLACK_BOT_TOKEN
  fi
  if [[ -n "${EXISTING_SLACK_SIGNING_SECRET}" ]]; then
    read -r -p "SLACK_SIGNING_SECRET (press Enter to keep existing): " _prompt_signing_secret
    if [[ -n "${_prompt_signing_secret}" ]]; then
      SLACK_SIGNING_SECRET="${_prompt_signing_secret}"
    fi
  elif [[ -z "${SLACK_SIGNING_SECRET}" ]]; then
    read -r -p "SLACK_SIGNING_SECRET (optional now): " SLACK_SIGNING_SECRET
  fi
  if [[ -n "${EXISTING_SLACK_APP_TOKEN}" ]]; then
    read -r -p "SLACK_APP_TOKEN (press Enter to keep existing): " _prompt_app_token
    if [[ -n "${_prompt_app_token}" ]]; then
      SLACK_APP_TOKEN="${_prompt_app_token}"
    fi
  elif [[ -z "${SLACK_APP_TOKEN}" ]]; then
    read -r -p "SLACK_APP_TOKEN (xapp-..., optional now): " SLACK_APP_TOKEN
  fi
fi

cat >"${MANIFEST_FILE}" <<EOF
display_information:
  name: ${APP_NAME}
  description: Conversational Slack broker for OpAMP diagnostics and operations.
  background_color: "#1a73e8"
features:
  bot_user:
    display_name: ${APP_NAME}
    always_online: false
  slash_commands:
    - command: ${SLASH_COMMAND}
      description: Query OpAMP status, health, config, and diagnostics.
      usage_hint: "[status|health|config|tools] <target>"
      should_escape: false
      url: https://example.invalid/slack/commands
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - channels:history
      - chat:write
      - commands
      - groups:history
      - im:history
      - im:write
      - mpim:history
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
EOF

if [[ -n "${SLACK_BOT_TOKEN}" ]]; then
  set_env_var "${ENV_FILE}" "SLACK_BOT_TOKEN" "${SLACK_BOT_TOKEN}"
fi
if [[ -n "${SLACK_SIGNING_SECRET}" ]]; then
  set_env_var "${ENV_FILE}" "SLACK_SIGNING_SECRET" "${SLACK_SIGNING_SECRET}"
fi
if [[ -n "${SLACK_APP_TOKEN}" ]]; then
  set_env_var "${ENV_FILE}" "SLACK_APP_TOKEN" "${SLACK_APP_TOKEN}"
fi
set_env_var "${ENV_FILE}" "BROKER_CONFIG_PATH" "./opamp_broker/config/broker.example.json"

cat <<EOF

Slack setup files prepared.
- Env file: ${ENV_FILE}
- Manifest: ${MANIFEST_FILE}

Next:
1. Follow docs/slack_configuration.md to create/install the Slack app from this manifest.
2. If you skipped tokens, rerun this script with --bot-token/--signing-secret/--app-token.
3. Start broker: ./scripts/start_broker.sh
EOF
