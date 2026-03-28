#!/usr/bin/env bash
set -euo pipefail

# Configures a local Keycloak container for OpAMP JWT bearer token testing.
# This script is idempotent and can be re-run safely.

KEYCLOAK_CONTAINER_NAME="${KEYCLOAK_CONTAINER_NAME:-opamp-keycloak}"
KEYCLOAK_IMAGE="${KEYCLOAK_IMAGE:-quay.io/keycloak/keycloak:26.2}"
KEYCLOAK_HOST_PORT="${KEYCLOAK_HOST_PORT:-8081}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-opamp}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-opamp-mcp}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-opamp-mcp-secret}"
KEYCLOAK_USER="${KEYCLOAK_USER:-opamp-user}"
KEYCLOAK_USER_PASSWORD="${KEYCLOAK_USER_PASSWORD:-opamp-password}"

KEYCLOAK_INTERNAL_URL="http://127.0.0.1:8080"
KEYCLOAK_EXTERNAL_URL="http://127.0.0.1:${KEYCLOAK_HOST_PORT}"

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

ensure_container_running() {
  if docker ps --format '{{.Names}}' | grep -Fx "${KEYCLOAK_CONTAINER_NAME}" >/dev/null 2>&1; then
    return
  fi
  if docker ps -a --format '{{.Names}}' | grep -Fx "${KEYCLOAK_CONTAINER_NAME}" >/dev/null 2>&1; then
    echo "Starting existing Keycloak container ${KEYCLOAK_CONTAINER_NAME}..."
    docker start "${KEYCLOAK_CONTAINER_NAME}" >/dev/null
    return
  fi
  echo "Creating Keycloak container ${KEYCLOAK_CONTAINER_NAME}..."
  docker run -d \
    --name "${KEYCLOAK_CONTAINER_NAME}" \
    -p "${KEYCLOAK_HOST_PORT}:8080" \
    -e KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN}" \
    -e KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}" \
    "${KEYCLOAK_IMAGE}" \
    start-dev >/dev/null
}

wait_for_keycloak() {
  echo "Waiting for Keycloak to become ready on ${KEYCLOAK_EXTERNAL_URL}..."
  for _attempt in $(seq 1 60); do
    if curl -fsS "${KEYCLOAK_EXTERNAL_URL}/realms/master/.well-known/openid-configuration" >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done
  echo "Keycloak did not become ready in time." >&2
  exit 1
}

kcadm() {
  docker exec "${KEYCLOAK_CONTAINER_NAME}" /opt/keycloak/bin/kcadm.sh "$@"
}

create_or_update_realm() {
  if ! kcadm get "realms/${KEYCLOAK_REALM}" >/dev/null 2>&1; then
    echo "Creating realm ${KEYCLOAK_REALM}..."
    kcadm create realms -s "realm=${KEYCLOAK_REALM}" -s enabled=true >/dev/null
  else
    echo "Realm ${KEYCLOAK_REALM} already exists."
  fi
}

create_or_update_client() {
  local client_query_json client_uuid
  client_query_json="$(kcadm get clients -r "${KEYCLOAK_REALM}" -q "clientId=${KEYCLOAK_CLIENT_ID}" --fields id,clientId --format json)"
  client_uuid="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["id"] if data else "")' <<<"${client_query_json}")"
  if [[ -z "${client_uuid}" ]]; then
    echo "Creating client ${KEYCLOAK_CLIENT_ID}..."
    client_uuid="$(kcadm create clients -r "${KEYCLOAK_REALM}" \
      -s "clientId=${KEYCLOAK_CLIENT_ID}" \
      -s enabled=true \
      -s protocol=openid-connect \
      -s publicClient=false \
      -s directAccessGrantsEnabled=true \
      -s standardFlowEnabled=true \
      -s serviceAccountsEnabled=true \
      -s "secret=${KEYCLOAK_CLIENT_SECRET}" \
      -i | tr -d '\r')"
  else
    echo "Client ${KEYCLOAK_CLIENT_ID} already exists; updating auth settings."
  fi
  kcadm update "clients/${client_uuid}" -r "${KEYCLOAK_REALM}" \
    -s enabled=true \
    -s protocol=openid-connect \
    -s publicClient=false \
    -s directAccessGrantsEnabled=true \
    -s standardFlowEnabled=true \
    -s serviceAccountsEnabled=true \
    -s "secret=${KEYCLOAK_CLIENT_SECRET}" >/dev/null
}

create_or_update_user() {
  local user_query_json user_uuid
  user_query_json="$(kcadm get users -r "${KEYCLOAK_REALM}" -q "username=${KEYCLOAK_USER}" --fields id,username --format json)"
  user_uuid="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["id"] if data else "")' <<<"${user_query_json}")"
  if [[ -z "${user_uuid}" ]]; then
    echo "Creating user ${KEYCLOAK_USER}..."
    kcadm create users -r "${KEYCLOAK_REALM}" \
      -s "username=${KEYCLOAK_USER}" \
      -s enabled=true >/dev/null
  else
    echo "User ${KEYCLOAK_USER} already exists; refreshing password."
  fi
  kcadm set-password -r "${KEYCLOAK_REALM}" \
    --username "${KEYCLOAK_USER}" \
    --new-password "${KEYCLOAK_USER_PASSWORD}" \
    --temporary false >/dev/null
}

main() {
  require_command docker
  require_command curl
  require_command python3

  ensure_container_running
  wait_for_keycloak

  echo "Authenticating Keycloak admin client..."
  kcadm config credentials \
    --server "${KEYCLOAK_INTERNAL_URL}" \
    --realm master \
    --user "${KEYCLOAK_ADMIN}" \
    --password "${KEYCLOAK_ADMIN_PASSWORD}" >/dev/null

  create_or_update_realm
  create_or_update_client
  create_or_update_user

  echo
  echo "Keycloak setup complete."
  echo "Realm: ${KEYCLOAK_REALM}"
  echo "Client ID: ${KEYCLOAK_CLIENT_ID}"
  echo "Client Secret: ${KEYCLOAK_CLIENT_SECRET}"
  echo "User: ${KEYCLOAK_USER}"
  echo "Issuer URL: ${KEYCLOAK_EXTERNAL_URL}/realms/${KEYCLOAK_REALM}"
  echo "JWKS URL: ${KEYCLOAK_EXTERNAL_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/certs"
  echo
  echo "Example provider auth env:"
  echo "  export OPAMP_AUTH_MODE=jwt"
  echo "  export OPAMP_AUTH_JWT_ISSUER=${KEYCLOAK_EXTERNAL_URL}/realms/${KEYCLOAK_REALM}"
  echo "  export OPAMP_AUTH_JWT_AUDIENCE=${KEYCLOAK_CLIENT_ID}"
  echo
  echo "Example token request:"
  echo "  curl -s -X POST \\"
  echo "    ${KEYCLOAK_EXTERNAL_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token \\"
  echo "    -d grant_type=password \\"
  echo "    -d client_id=${KEYCLOAK_CLIENT_ID} \\"
  echo "    -d client_secret=${KEYCLOAK_CLIENT_SECRET} \\"
  echo "    -d username=${KEYCLOAK_USER} \\"
  echo "    -d password=${KEYCLOAK_USER_PASSWORD}"
}

main "$@"
