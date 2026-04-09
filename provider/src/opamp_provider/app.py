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

"""Quart OpAMP server skeleton."""

from __future__ import annotations

import asyncio
import json
import ssl
from typing import Callable
import logging
import os
import pathlib
import signal
import tracemalloc
from http import HTTPStatus
from datetime import datetime, timedelta, timezone

from google.protobuf import text_format
from quart import Quart, Response, jsonify, redirect, request, websocket
from werkzeug.exceptions import HTTPException

from opamp_provider import config as provider_config
from opamp_provider import auth as provider_auth
from opamp_provider.command_record import CommandRecord
from opamp_provider.commands import (
    command_object_factory,
    get_command_metadata,
    get_custom_capabilities_list,
)
from opamp_provider.exceptions import ServerToAgentException
from opamp_provider.mcptool import register_mcp_transport, register_tool_routes
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import STORE, ClientRecord
from opamp_provider.state_persistence import (
    list_snapshot_files,
    prune_snapshot_files,
    save_state_snapshot,
)
from opamp_provider.transport import decode_message, encode_message
from shared.opamp_config import (
    OPAMP_HTTP_PATH,
    OPAMP_TRANSPORT_HEADER_NONE,
    PB_FIELD_COMMAND,
    PB_FIELD_CONNECTION_SETTINGS_REQUEST,
    PB_FIELD_CUSTOM_MESSAGE,
    PB_FIELD_PACKAGE_STATUSES,
    ServerCapabilities,
    UTF8_ENCODING,
)

app = Quart("opamp_server")
app.config.setdefault("DIAGNOSTIC_MODE", False)
register_tool_routes(app)
register_mcp_transport(app)
logger = logging.getLogger(__name__)
tracemalloc.start()

CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
LOG_HTTP_MSG = "opamp http AgentToServer:\n%s"  # Log format for HTTP messages.
LOG_WS_MSG = "opamp ws AgentToServer:\n%s"  # Log format for WebSocket messages.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
LOG_REST_COMMAND = "queued command for client %s classifier=%s action=%s at %s"  # Log format for queued REST-originated commands.
LOG_SEND_COMMAND = "sent command to client %s at %s"  # Log format for command dispatch completion.
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.
SERVER_CAPABILITIES = int(ServerCapabilities.AcceptsStatus)  # Server advertises AcceptsStatus only.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30  # Fallback heartbeat interval for connection settings offers.
MODEL_DUMP_MODE = "json"  # Pydantic model_dump mode used for API JSON payloads.
CERT_NOT_AFTER_SUFFIX_GMT = " GMT"  # Trailing timezone marker emitted by ssl certificate decoder.
CERT_NOT_AFTER_PARSE_FORMAT = "%b %d %H:%M:%S %Y"  # Datetime parse format for decoded certificate notAfter values.
TLS_EXPIRY_WARNING_DAYS = 30  # Number of days before expiry to highlight certificate warning state.

COMMAND_RESTART = "restart"  # Standard OpAMP restart command action name.
COMMAND_FORCE_RESYNC = "forceresync"  # Custom action name used to trigger full state resync.
COMMAND_CHATOP = "chatopcommand"  # Custom action name for ChatOps command dispatch.
COMMAND_SHUTDOWN_AGENT = "shutdownagent"  # Custom action name for remote shutdown requests.
COMMAND_NULLCOMMAND = "nullcommand"  # Custom no-op action used for testing command plumbing.
CLASSIFIER_COMMAND = "command"  # Classifier used for standard OpAMP commands.
CLASSIFIER_CUSTOM_COMMAND = "custom_command"  # Classifier used for provider custom command routing.
CLASSIFIER_CUSTOM = "custom"  # Alternate classifier value emitted by some custom command builders.
CHANNEL_HTTP = "HTTP"  # Client channel label for HTTP transport.
CHANNEL_WEBSOCKET = "websocket"  # Client channel label for WebSocket transport.
ACTION_APPLY_CONFIG = "apply_config"  # Next-action token to build remote_config payload.
ACTION_CHANGE_CONNECTIONS = "change_connections"  # Next-action token to build connection settings payload.
ACTION_PACKAGE_AVAILABLE = "package_availabe"  # Next-action token to build packages available payload.
ACTION_COMMAND_AGENT = "command_agent"  # Next-action token to send an OpAMP standard command.
ACTION_CUSTOM_AGENT_COMMAND = "custom_agent_command"  # Next-action token to send a custom capability command.
# Allowed next-action values accepted by /rest/nextAction.
ACTION_OPTIONS = {
    ACTION_APPLY_CONFIG,
    ACTION_CHANGE_CONNECTIONS,
    ACTION_PACKAGE_AVAILABLE,
    ACTION_COMMAND_AGENT,
    ACTION_CUSTOM_AGENT_COMMAND,
}
GLOBAL_SETTINGS_HELP: dict[str, dict[str, str]] = {
    "delayed_comms_seconds": {
        "label": "Delayed Communications Threshold (seconds)",
        "tooltip": (
            "Seconds before a client is marked delayed (amber). "
            "This overrides the config file value."
        ),
    },
    "significant_comms_seconds": {
        "label": "Significant Communications Threshold (seconds)",
        "tooltip": (
            "Seconds before a client is marked late (red). "
            "Must be greater than delayed_comms_seconds. "
            "This overrides the config file value."
        ),
    },
    "client_event_history_size": {
        "label": "Client Event History Size",
        "tooltip": (
            "Maximum number of recent per-client events retained by the provider. "
            "Older events are dropped when this limit is exceeded."
        ),
    },
    "human_in_loop_approval": {
        "label": "Human In Loop Approval",
        "tooltip": (
            "When enabled, unknown agents are staged for manual review and remain "
            "blocked from normal processing until approved."
        ),
    },
    "state_save_folder": {
        "label": "State Save Folder",
        "tooltip": (
            "Folder path where provider state snapshots are written and restored from."
        ),
    },
    "retention_count": {
        "label": "State Snapshot Retention Count",
        "tooltip": (
            "Number of latest provider state snapshot files to retain."
        ),
    },
    "autosave_interval_seconds_since_change": {
        "label": "Autosave Interval Since Change (seconds)",
        "tooltip": (
            "Seconds between autosaves for non-heartbeat OpAMP state changes."
        ),
    },
    "default_heartbeat_frequency": {
        "label": "Default Heartbeat Frequency (seconds)",
        "tooltip": (
            "Default heartbeat interval in seconds applied to clients when globally updated."
        ),
    },
}
_SHUTDOWN_REQUESTED = False  # Guard to prevent duplicate shutdown scheduling.
_LAST_DISCONNECT_PURGE: datetime | None = None  # Timestamp of last disconnected-client purge pass.
_WEBSOCKET_CLIENTS: dict[object, str | None] = {}  # Active websocket -> client_id mapping.
_LAST_AUTOSAVE_ELIGIBLE_CHANGE_AT: datetime | None = None  # Timestamp of first unsaved non-heartbeat OpAMP state change.
_PERSISTENCE_STATUS: dict[str, object] = {
    "restore_status": "not_requested",
    "restore_detail": "",
    "last_save_status": "not_run",
    "last_save_path": None,
    "last_save_reason": None,
    "last_save_at": None,
}
ERR_AGENT_PENDING_APPROVAL = "agent pending approval"
ERR_AGENT_BLOCKED = "agent is blocked"
ERR_AGENT_AUTH_FAILED = "agent authentication failed"
ERR_OPAMP_AUTH_CONFIG_INVALID = "invalid opamp-use-authorization configuration"
ERR_UI_AUTH_CONFIG_INVALID = "invalid ui-use-authorization configuration"

# Keep in-memory client heartbeat defaults aligned with loaded provider config.
STORE.set_default_heartbeat_frequency(
    provider_config.CONFIG.default_heartbeat_frequency,
    max_events=provider_config.CONFIG.client_event_history_size,
    record_event=False,
)


def set_state_restore_status(status: str, detail: str = "") -> None:
    """Record persisted-state restore status for diagnostics and logs."""
    _PERSISTENCE_STATUS["restore_status"] = str(status).strip() or "unknown"
    _PERSISTENCE_STATUS["restore_detail"] = str(detail or "")


def _record_snapshot_status(
    *,
    status: str,
    path: str | None,
    reason: str,
    at: datetime | None = None,
) -> None:
    """Record latest snapshot save status for diagnostics."""
    _PERSISTENCE_STATUS["last_save_status"] = str(status).strip() or "unknown"
    _PERSISTENCE_STATUS["last_save_path"] = path
    _PERSISTENCE_STATUS["last_save_reason"] = reason
    _PERSISTENCE_STATUS["last_save_at"] = (
        (at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    )


def _is_heartbeat_only_message(agent_msg: opamp_pb2.AgentToServer) -> bool:
    """Return whether AgentToServer payload only contains instance_uid/sequence_num."""
    field_names = {descriptor.name for descriptor, _value in agent_msg.ListFields()}
    if not field_names:
        return False
    return field_names.issubset({"instance_uid", "sequence_num"})


def _save_state_snapshot(reason: str) -> None:
    """Save one persisted-state snapshot if persistence is enabled."""
    persistence = provider_config.CONFIG.state_persistence
    if persistence.enabled is not True:
        return
    now = datetime.now(timezone.utc)
    try:
        path = save_state_snapshot(
            store=STORE,
            persistence=persistence,
            reason=reason,
            logger=logger,
            now=now,
        )
        _record_snapshot_status(
            status="saved",
            path=str(path) if path is not None else None,
            reason=reason,
            at=now,
        )
    except Exception as exc:
        logger.exception("state snapshot save failed reason=%s", reason, exc_info=exc)
        _record_snapshot_status(
            status="failed",
            path=None,
            reason=reason,
            at=now,
        )


def _note_non_heartbeat_state_change_and_maybe_autosave() -> None:
    """Track non-heartbeat state change timing and run autosave checks."""
    global _LAST_AUTOSAVE_ELIGIBLE_CHANGE_AT
    now = datetime.now(timezone.utc)
    if _LAST_AUTOSAVE_ELIGIBLE_CHANGE_AT is None:
        _LAST_AUTOSAVE_ELIGIBLE_CHANGE_AT = now

    persistence = provider_config.CONFIG.state_persistence
    if persistence.enabled is not True:
        return
    interval = max(1, int(persistence.autosave_interval_seconds_since_change))
    elapsed = (now - _LAST_AUTOSAVE_ELIGIBLE_CHANGE_AT).total_seconds()
    if elapsed < interval:
        return
    _save_state_snapshot("autosave_non_heartbeat_opamp")
    _LAST_AUTOSAVE_ELIGIBLE_CHANGE_AT = None


def _state_snapshot_file_count() -> int:
    """Return count of snapshot files currently present for configured prefix."""
    try:
        prefix = provider_config.CONFIG.state_persistence.state_file_prefix
        return len(list_snapshot_files(prefix))
    except Exception as exc:
        logger.warning("failed counting state snapshot files", exc_info=exc)
        return 0


def _request_process_shutdown() -> None:
    """Trigger a process shutdown via SIGINT (fallback to immediate exit)."""
    try:
        os.kill(os.getpid(), signal.SIGINT)
    except Exception:
        os._exit(0)


async def _shutdown_after_response() -> None:
    """Delay briefly to flush responses before shutting down."""
    await asyncio.sleep(0.2)
    _request_process_shutdown()


@app.errorhandler(Exception)
async def handle_unexpected_error(error: Exception) -> Response:
    """Return JSON for unexpected errors while preserving HTTPException behavior."""
    if isinstance(error, HTTPException):
        return error
    logger.exception("Unhandled app error", exc_info=error)
    return jsonify({"error": "internal server error"}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.before_request
async def enforce_bearer_auth() -> Response | None:
    """Apply non-OpAMP bearer-token auth using provider.ui-use-authorization."""
    if request.path == OPAMP_HTTP_PATH:
        return None
    decision = _evaluate_non_opamp_http_auth(
        path=request.path,
        method=request.method,
        authorization_header=request.headers.get("Authorization"),
        remote_addr=request.remote_addr,
    )
    if decision.allowed:
        return None
    response = jsonify({"error": decision.error})
    if decision.status_code == HTTPStatus.UNAUTHORIZED:
        response.headers["WWW-Authenticate"] = provider_auth.WWW_AUTHENTICATE_BEARER
    return response, decision.status_code


def _extract_client_id(agent_msg: opamp_pb2.AgentToServer) -> str:
    """Return hex-encoded instance UID when present; otherwise an empty string."""
    if not agent_msg.instance_uid:
        return ""
    return agent_msg.instance_uid.hex()


def _request_header_map() -> dict[str, str]:
    """Return request headers as a plain dictionary for audit logging/auth checks."""
    return {str(key): str(value) for key, value in request.headers.items()}


def _websocket_header_map() -> dict[str, str]:
    """Return websocket handshake headers as a plain dictionary."""
    return {str(key): str(value) for key, value in websocket.headers.items()}


def _websocket_remote_addr() -> str | None:
    """Return websocket remote address when available."""
    client_info = getattr(websocket, "client", None)
    if isinstance(client_info, tuple) and client_info:
        return str(client_info[0])
    return None


def _diagnostic_mode_enabled() -> bool:
    """Return whether server diagnostic mode is enabled."""
    return bool(app.config.get("DIAGNOSTIC_MODE", False))


def _coerce_bool_setting(value: object, *, key: str) -> bool:
    """Coerce UI/API boolean payload values for settings endpoints."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{key} must be a boolean")


def _load_tls_certificate_expiry_utc(cert_file: str) -> datetime | None:
    """Load certificate expiry timestamp in UTC from a PEM certificate file."""
    try:
        cert_data = ssl._ssl._test_decode_cert(cert_file)
    except Exception as exc:
        logger.warning(
            "failed to decode provider tls cert file %s", cert_file, exc_info=exc
        )
        return None
    not_after_raw = cert_data.get("notAfter")
    if not isinstance(not_after_raw, str) or not not_after_raw.strip():
        return None
    normalized_not_after = not_after_raw.strip()
    if normalized_not_after.endswith(CERT_NOT_AFTER_SUFFIX_GMT):
        normalized_not_after = normalized_not_after[: -len(CERT_NOT_AFTER_SUFFIX_GMT)]
    normalized_not_after = " ".join(normalized_not_after.split())
    try:
        parsed = datetime.strptime(normalized_not_after, CERT_NOT_AFTER_PARSE_FORMAT)
    except ValueError:
        logger.warning(
            "failed to parse provider tls cert notAfter value %r",
            not_after_raw,
        )
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _tls_certificate_expiry_metadata(
    *,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    """Build TLS certificate-expiry metadata for global settings responses."""
    tls_config = provider_config.CONFIG.tls
    if tls_config is None:
        return {
            "tls_enabled": False,
            "https_certificate_expiry_date": None,
            "https_certificate_days_remaining": None,
            "https_certificate_expiring_soon": False,
        }
    expiry_utc = _load_tls_certificate_expiry_utc(tls_config.cert_file)
    if expiry_utc is None:
        return {
            "tls_enabled": True,
            "https_certificate_expiry_date": None,
            "https_certificate_days_remaining": None,
            "https_certificate_expiring_soon": False,
        }
    now = now_utc or datetime.now(timezone.utc)
    days_remaining = (expiry_utc.date() - now.date()).days
    return {
        "tls_enabled": True,
        "https_certificate_expiry_date": expiry_utc.date().isoformat(),
        "https_certificate_days_remaining": days_remaining,
        "https_certificate_expiring_soon": days_remaining <= TLS_EXPIRY_WARNING_DAYS,
    }


def _header_value(
    *,
    headers: dict[str, str],
    name: str,
) -> str | None:
    """Return a case-insensitive header value from a plain header dictionary."""
    for key, value in headers.items():
        if str(key).strip().lower() == name.lower():
            return str(value)
    return None


def _provider_authorization_mode_to_auth_mode(
    provider_mode: str,
) -> str | None:
    """Map provider config authorization values to auth module mode."""
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_NONE:
        return provider_auth.AUTH_MODE_DISABLED
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN:
        return provider_auth.AUTH_MODE_STATIC
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_IDP:
        return provider_auth.AUTH_MODE_JWT
    return None


def _evaluate_opamp_transport_auth(
    *,
    headers: dict[str, str],
    remote_addr: str | None,
    channel: str,
) -> provider_auth.AuthDecision:
    """Authorize OpAMP transport requests using provider config mode."""
    opamp_mode = str(provider_config.CONFIG.opamp_use_authorization).strip().lower()
    mapped_mode = _provider_authorization_mode_to_auth_mode(opamp_mode)
    if mapped_mode is None:
        logger.error(
            "unsupported provider.%s value=%s",
            provider_config.CFG_OPAMP_USE_AUTHORIZATION,
            opamp_mode,
        )
        return provider_auth.AuthDecision(
            allowed=False,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            error=ERR_OPAMP_AUTH_CONFIG_INVALID,
            reason=f"unsupported mode {opamp_mode}",
        )
    authorization_header = _header_value(headers=headers, name="Authorization")
    method = "POST" if channel == CHANNEL_HTTP else "WEBSOCKET"
    return provider_auth.evaluate_required_bearer_auth(
        mode=mapped_mode,
        path=OPAMP_HTTP_PATH,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
        static_token=provider_auth.OPAMP_AUTH_SETTINGS.static_token,
        jwt_settings=provider_auth.OPAMP_AUTH_SETTINGS,
    )


def _evaluate_non_opamp_http_auth(
    *,
    path: str,
    method: str,
    authorization_header: str | None,
    remote_addr: str | None,
) -> provider_auth.AuthDecision:
    """Authorize non-OpAMP HTTP requests using provider.ui-use-authorization."""
    ui_mode = str(provider_config.CONFIG.ui_use_authorization).strip().lower()
    mapped_mode = _provider_authorization_mode_to_auth_mode(ui_mode)
    if mapped_mode is None:
        logger.error(
            "unsupported provider.%s value=%s",
            provider_config.CFG_UI_USE_AUTHORIZATION,
            ui_mode,
        )
        return provider_auth.AuthDecision(
            allowed=False,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            error=ERR_UI_AUTH_CONFIG_INVALID,
            reason=f"unsupported mode {ui_mode}",
        )
    return provider_auth.evaluate_required_bearer_auth(
        mode=mapped_mode,
        path=path,
        method=method,
        authorization_header=authorization_header,
        remote_addr=remote_addr,
        static_token=provider_auth.UI_AUTH_SETTINGS.static_token,
        jwt_settings=provider_auth.UI_AUTH_SETTINGS,
    )


def _build_error_message(
    *,
    instance_uid: bytes | None,
    error_message: str,
    error_type: opamp_pb2.ServerErrorResponseType = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    ),
) -> opamp_pb2.ServerToAgent:
    """Build a ServerToAgent error payload without requiring prior response state."""
    response = opamp_pb2.ServerToAgent()
    if instance_uid:
        response.instance_uid = instance_uid
    response.error_response.type = error_type
    response.error_response.error_message = error_message
    return response


def _build_opamp_http_error_response(
    *,
    instance_uid: bytes | None,
    status_code: int,
    error_message: str,
    headers: dict[str, str] | None = None,
    error_type: opamp_pb2.ServerErrorResponseType = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    ),
) -> Response:
    """Build a protobuf HTTP response carrying a ServerToAgent error payload."""
    payload = _build_error_message(
        instance_uid=instance_uid,
        error_message=error_message,
        error_type=error_type,
    ).SerializeToString()
    response = Response(
        payload,
        content_type=CONTENT_TYPE_PROTO,
        status=status_code,
    )
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    return response


def _log_blocked_agent_attempt(
    *,
    client_id: str,
    channel: str,
    headers: dict[str, str],
    remote_addr: str | None,
) -> None:
    """Log one blocked-agent request with headers for audit visibility."""
    logger.warning(
        "blocked agent rejected client_id=%s channel=%s remote_addr=%s headers=%s",
        client_id or "missing",
        channel,
        remote_addr or "unknown",
        headers,
    )


def _build_apply_config(response: opamp_pb2.ServerToAgent) -> opamp_pb2.ServerToAgent:
    """Attach a remote_config action to the ServerToAgent response."""
    logger.info("building next action payload: %s", ACTION_APPLY_CONFIG)
    response.remote_config.SetInParent()
    return response


def _build_change_connections(
    response: opamp_pb2.ServerToAgent,
    client: ClientRecord | None = None,
) -> opamp_pb2.ServerToAgent:
    """Build connection settings update payload for the client heartbeat interval."""
    logger.info("building next action payload: %s", ACTION_CHANGE_CONNECTIONS)
    raw_interval = (
        getattr(client, "heartbeat_frequency", DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
        if client is not None
        else DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    )
    try:
        interval_seconds = max(1, int(raw_interval))
    except (TypeError, ValueError):
        interval_seconds = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    response.connection_settings.opamp.heartbeat_interval_seconds = interval_seconds
    logger.info(
        "set connection_settings.opamp.heartbeat_interval_seconds=%s for client_id=%s",
        interval_seconds,
        client.client_id if client is not None else "unknown",
    )
    return response


def _build_package_available(
    response: opamp_pb2.ServerToAgent,
) -> opamp_pb2.ServerToAgent:
    """Return a not-available error for package availability action."""
    logger.info("building next action payload: %s", ACTION_PACKAGE_AVAILABLE)
    # response.packages_available.SetInParent()
    response = _build_error(
        msg=response, error_message="Package Availability feature not available"
    )
    return response


def _build_agent_remote_config(
    response: opamp_pb2.ServerToAgent, request_msg: opamp_pb2.AgentToServer
) -> opamp_pb2.ServerToAgent:
    """Placeholder builder for AgentRemoteConfig server offers."""
    logger.info("remote config TBD")
    return response


def _build_connection_settings_offers(
    response: opamp_pb2.ServerToAgent, request_msg: opamp_pb2.AgentToServer
) -> opamp_pb2.ServerToAgent:
    """Placeholder builder for ConnectionSettingsOffers server offers."""
    logger.info("connection settings TBD")
    return response


def _build_packages_available(
    response: opamp_pb2.ServerToAgent, request_msg: opamp_pb2.AgentToServer
) -> opamp_pb2.ServerToAgent:
    """Placeholder builder for PackagesAvailable server offers."""
    logger.info("packages available: TBD")
    return response


def _build_offer_payloads(
    response: opamp_pb2.ServerToAgent, request_msg: opamp_pb2.AgentToServer
) -> opamp_pb2.ServerToAgent:
    """Apply placeholder offer builders for request-driven server payloads."""
    response = _build_agent_remote_config(response, request_msg)
    response = _build_connection_settings_offers(response, request_msg)
    response = _build_packages_available(response, request_msg)
    return response


def _build_restart_command(
    response: opamp_pb2.ServerToAgent, pending_command: CommandRecord
) -> opamp_pb2.ServerToAgent:
    """Build a restart ServerToAgentCommand payload."""
    logger.info(
        "building command payload classifier=%s action=%s",
        pending_command.classifier,
        pending_command.action,
    )
    response.command.type = opamp_pb2.CommandType.CommandType_Restart
    logger.debug(
        "created ServerToAgent.command payload: %s",
        text_format.MessageToString(response.command).strip(),
    )
    return response


def _build_force_resync_command(
    response: opamp_pb2.ServerToAgent, pending_command: CommandRecord
) -> opamp_pb2.ServerToAgent:
    """Build a report-full-state ServerToAgent flags payload."""
    logger.info(
        "building command payload classifier=%s action=%s",
        pending_command.classifier,
        pending_command.action,
    )
    response.flags = response.flags | int(
        opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportFullState
    )
    logger.debug("created ServerToAgent.flags payload: %s", response.flags)
    return response


def _kv_lookup(pairs: list[dict[str, str]], key: str) -> str:
    """Fetch a string value from a list of key/value dictionaries."""
    for pair in pairs:
        if pair.get("key", "").strip().lower() == key.lower():
            return str(pair.get("value", "")).strip()
    return ""


def _build_custom_command_payload(
    response: opamp_pb2.ServerToAgent, pending_command: CommandRecord
) -> opamp_pb2.ServerToAgent:
    """Build a ServerToAgent custom message payload from queued key/value pairs."""
    logger.info(
        "building custom command payload classifier=%s action=%s",
        pending_command.classifier,
        pending_command.action,
    )
    classifier = (pending_command.classifier or "").strip().lower()
    action = (pending_command.action or "").strip().lower()
    if classifier == CLASSIFIER_CUSTOM:
        try:
            command_obj = command_object_factory(
                classifier=classifier,
                key_values={
                    pair["key"]: pair["value"]
                    for pair in pending_command.key_value_pairs
                },
            )
            if hasattr(command_obj, "to_custom_message"):
                response.custom_message.CopyFrom(command_obj.to_custom_message())
                logger.debug(
                    "created ServerToAgent.custom_message payload from custom command object: %s",
                    text_format.MessageToString(response.custom_message).strip(),
                )
                return response
        except ValueError:
            logger.debug(
                "no concrete custom command object for action=%s; using generic payload builder",
                action,
            )

    capability = _kv_lookup(pending_command.key_value_pairs, "capability")
    custom_type = _kv_lookup(pending_command.key_value_pairs, "type")
    data_value = _kv_lookup(pending_command.key_value_pairs, "data")

    response.custom_message.capability = capability or "custom_command"
    response.custom_message.type = custom_type or pending_command.action
    if data_value:
        response.custom_message.data = data_value.encode(UTF8_ENCODING)
    else:
        response.custom_message.data = b""
    logger.debug(
        "created ServerToAgent.custom_message payload: %s",
        text_format.MessageToString(response.custom_message).strip(),
    )
    return response


COMMAND_BUILDERS: dict[
    tuple[str, str],
    Callable[[opamp_pb2.ServerToAgent, CommandRecord], opamp_pb2.ServerToAgent],
] = {
    (CLASSIFIER_COMMAND, COMMAND_RESTART): _build_restart_command,
    (CLASSIFIER_COMMAND, COMMAND_FORCE_RESYNC): _build_force_resync_command,
    (CLASSIFIER_CUSTOM, COMMAND_CHATOP): _build_custom_command_payload,
    (CLASSIFIER_CUSTOM, COMMAND_SHUTDOWN_AGENT): _build_custom_command_payload,
    (CLASSIFIER_CUSTOM, COMMAND_NULLCOMMAND): _build_custom_command_payload,
    (CLASSIFIER_CUSTOM_COMMAND, "*"): _build_custom_command_payload,
}


def _apply_command_intent(
    response: opamp_pb2.ServerToAgent, pending_command: CommandRecord | None
) -> opamp_pb2.ServerToAgent:
    """Map classifier/action to a payload builder and apply it to the response."""
    if pending_command is None:
        return response
    classifier = pending_command.classifier.strip().lower()
    action = pending_command.action.strip().lower()
    builder = COMMAND_BUILDERS.get((classifier, action))
    if builder is None:
        builder = COMMAND_BUILDERS.get((classifier, "*"))
    if builder is None:
        logger.warning(
            "No command builder for classifier=%s action=%s",
            classifier,
            action,
        )
        return response
    updated_response = builder(response, pending_command)
    logger.debug(
        "created command intent payload summary client classifier=%s action=%s has_command=%s has_custom_message=%s",
        classifier,
        action,
        updated_response.HasField(PB_FIELD_COMMAND),
        updated_response.HasField(PB_FIELD_CUSTOM_MESSAGE),
    )
    return updated_response


def _apply_next_action(
    response: opamp_pb2.ServerToAgent,
    *,
    action: str,
    pending_command: CommandRecord | None,
    client: ClientRecord | None = None,
) -> opamp_pb2.ServerToAgent:
    """Dispatch the next action string to the correct builder."""
    if action == ACTION_APPLY_CONFIG:
        return _build_apply_config(response)
    if action == ACTION_CHANGE_CONNECTIONS:
        return _build_change_connections(response, client)
    if action == ACTION_PACKAGE_AVAILABLE:
        return _build_package_available(response)
    if action == ACTION_COMMAND_AGENT:
        return _apply_command_intent(response, pending_command)
    if action == ACTION_CUSTOM_AGENT_COMMAND:
        return _apply_command_intent(response, pending_command)
    logger.warning("unknown next action: %s", action)
    return response


def _build_response(
    request_msg: opamp_pb2.AgentToServer,
    pending_command: CommandRecord | None,
    client: ClientRecord | None = None,
    channel: str | None = None,
) -> opamp_pb2.ServerToAgent:
    """Build a minimal ServerToAgent response for a request."""
    response = opamp_pb2.ServerToAgent()
    if request_msg.instance_uid:
        response.instance_uid = request_msg.instance_uid
        logger.info("set response to: %s", response.instance_uid)
    else:
        logger.warning("Cant set response instance_uid")

    # Server capability advertisement is fixed to AcceptsStatus.
    response.capabilities = SERVER_CAPABILITIES
    custom_capabilities = get_custom_capabilities_list()
    if custom_capabilities:
        response.custom_capabilities.capabilities.extend(custom_capabilities)
    if client:
        pending_identification = STORE.pop_agent_identification(client.client_id)
        if pending_identification:
            response.agent_identification.new_instance_uid = pending_identification
    response = _build_offer_payloads(response, request_msg)
    if channel == CHANNEL_HTTP and client:
        next_action = STORE.pop_next_action(client.client_id)
        if next_action:
            response = _apply_next_action(
                response,
                action=next_action,
                pending_command=pending_command,
                client=client,
            )
    response = _apply_command_intent(response, pending_command)
    return response


def _has_dispatched_command_payload(response_msg: opamp_pb2.ServerToAgent) -> bool:
    """Return whether a queued command was encoded in this response message."""
    return (
        response_msg.HasField(PB_FIELD_COMMAND)
        or response_msg.HasField(PB_FIELD_CUSTOM_MESSAGE)
        or bool(response_msg.flags)
    )


def _build_error(
    msg: opamp_pb2.ServerToAgent,
    error_type: opamp_pb2.ServerErrorResponseType = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    ),
    error_message: str = "Bad Request",
) -> opamp_pb2.ServerToAgent:
    """Build an error response and append error details to the message."""
    response = msg
    if not response.instance_uid:
        raise ServerToAgentException("no instance UID set")

    if not response.error_response:
        response.error_response = opamp_pb2.ErrorResponseType

    response.error_response.type = error_type

    if not response.error_response.error_message:
        response.error_response.error_message = error_message
    else:
        response.error_response.error_message = (
            response.error_response.error_message + "\n" + error_message
        )

    if (
        error_type
        == opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable
    ):
        retry_ns = int(provider_config.CONFIG.retry_after_seconds) * 1_000_000_000
        response.error_response.retry_info.retry_after_nanoseconds = retry_ns

    logging.getLogger(__name__).info(
        "Constructed an error response to transmit: %s",
        response.error_response,
    )
    return response


@app.post(OPAMP_HTTP_PATH)
async def opamp_http() -> Response:
    """Handle OpAMP HTTP POST requests."""
    try:
        data = await request.get_data()
        agent_msg = opamp_pb2.AgentToServer()
        if data:
            agent_msg.ParseFromString(data)

        logger.info(LOG_HTTP_MSG, text_format.MessageToString(agent_msg))
        client_id = _extract_client_id(agent_msg)
        request_headers = _request_header_map()
        remote_addr = request.remote_addr

        if client_id and STORE.is_blocked_agent(client_id):
            _log_blocked_agent_attempt(
                client_id=client_id,
                channel=CHANNEL_HTTP,
                headers=request_headers,
                remote_addr=remote_addr,
            )
            return _build_opamp_http_error_response(
                instance_uid=agent_msg.instance_uid if agent_msg.instance_uid else None,
                status_code=HTTPStatus.FORBIDDEN,
                error_message=ERR_AGENT_BLOCKED,
                error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
            )

        opamp_auth_decision = _evaluate_opamp_transport_auth(
            headers=request_headers,
            remote_addr=remote_addr,
            channel=CHANNEL_HTTP,
        )
        if not opamp_auth_decision.allowed:
            response_headers: dict[str, str] = {}
            if opamp_auth_decision.status_code == HTTPStatus.UNAUTHORIZED:
                response_headers["WWW-Authenticate"] = (
                    provider_auth.WWW_AUTHENTICATE_BEARER
                )
            error_type = (
                opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable
                if opamp_auth_decision.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
                else opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
            )
            return _build_opamp_http_error_response(
                instance_uid=agent_msg.instance_uid if agent_msg.instance_uid else None,
                status_code=opamp_auth_decision.status_code,
                error_message=opamp_auth_decision.error or ERR_AGENT_AUTH_FAILED,
                headers=response_headers,
                error_type=error_type,
            )

        known_client = STORE.get(client_id) if client_id else None
        if provider_config.CONFIG.human_in_loop_approval:
            if not client_id:
                return _build_opamp_http_error_response(
                    instance_uid=None,
                    status_code=HTTPStatus.BAD_REQUEST,
                    error_message="instance_uid is required when human_in_loop_approval is enabled",
                )
            if known_client is None:
                if STORE.get_pending_approval(client_id) is None:
                    try:
                        STORE.add_pending_approval_from_agent_msg(
                            agent_msg,
                            channel=CHANNEL_HTTP,
                            remote_addr=remote_addr,
                        )
                        logger.info(
                            "agent moved to pending approval client_id=%s remote_addr=%s",
                            client_id,
                            remote_addr or "unknown",
                        )
                    except Exception as approval_error:
                        STORE.block_agent(
                            client_id,
                            reason=f"failed pending approval payload transformation: {approval_error}",
                            headers=request_headers,
                            ip=remote_addr,
                        )
                        logger.exception(
                            "failed to transform pending approval payload; client blocked client_id=%s",
                            client_id,
                            exc_info=approval_error,
                        )
                        return _build_opamp_http_error_response(
                            instance_uid=(
                                agent_msg.instance_uid if agent_msg.instance_uid else None
                            ),
                            status_code=HTTPStatus.FORBIDDEN,
                            error_message=ERR_AGENT_BLOCKED,
                            error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                        )
                return _build_opamp_http_error_response(
                    instance_uid=agent_msg.instance_uid if agent_msg.instance_uid else None,
                    status_code=HTTPStatus.FORBIDDEN,
                    error_message=ERR_AGENT_PENDING_APPROVAL,
                    error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                )

        unsupported = []
        if agent_msg.HasField(PB_FIELD_PACKAGE_STATUSES):
            unsupported.append(PB_FIELD_PACKAGE_STATUSES)
        if agent_msg.HasField(PB_FIELD_CONNECTION_SETTINGS_REQUEST):
            unsupported.append(PB_FIELD_CONNECTION_SETTINGS_REQUEST)
        if unsupported:
            response_msg = opamp_pb2.ServerToAgent()
            response_msg.instance_uid = agent_msg.instance_uid
            response_msg = _build_error(
                error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                error_message=(f"unsupported fields: {', '.join(unsupported)}"),
                msg=response_msg,
            )
            payload = response_msg.SerializeToString()
            return Response(
                payload,
                content_type=CONTENT_TYPE_PROTO,
                status=HTTPStatus.BAD_REQUEST,
            )
        client = STORE.upsert_from_agent_msg(
            agent_msg,
            channel=CHANNEL_HTTP,
            remote_addr=remote_addr,
        )
        if not _is_heartbeat_only_message(agent_msg):
            _note_non_heartbeat_state_change_and_maybe_autosave()
        pending_command = STORE.next_pending_command(client.client_id)
        response_msg = _build_response(
            agent_msg,
            pending_command,
            client=client,
            channel=CHANNEL_HTTP,
        )
        payload = response_msg.SerializeToString()
        if pending_command is not None and _has_dispatched_command_payload(
            response_msg
        ):
            STORE.mark_command_sent(client.client_id, pending_command)
            logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))
        return Response(payload, content_type=CONTENT_TYPE_PROTO)
    except Exception as exc:
        logger.exception("Unhandled HTTP error - %s", exc_info=exc)
        response_msg = _build_error_message(
            instance_uid=None,
            error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable,
            error_message="internal server error",
        )
        payload = response_msg.SerializeToString()
        return Response(
            payload,
            content_type=CONTENT_TYPE_PROTO,
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@app.websocket(OPAMP_HTTP_PATH)
async def opamp_websocket() -> None:
    """Handle OpAMP WebSocket connections."""
    _WEBSOCKET_CLIENTS[websocket] = None
    ws_headers = _websocket_header_map()
    remote_addr = _websocket_remote_addr()
    try:
        opamp_auth_decision = _evaluate_opamp_transport_auth(
            headers=ws_headers,
            remote_addr=remote_addr,
            channel=CHANNEL_WEBSOCKET,
        )
        if not opamp_auth_decision.allowed:
            error_type = (
                opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable
                if opamp_auth_decision.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
                else opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
            )
            response_msg = _build_error_message(
                instance_uid=None,
                error_type=error_type,
                error_message=opamp_auth_decision.error or ERR_AGENT_AUTH_FAILED,
            )
            await websocket.send(encode_message(response_msg.SerializeToString()))
            await websocket.close(code=1008)
            return

        while True:
            pending_command = None
            client = None
            close_after_send = False
            data = await websocket.receive()
            if isinstance(data, str):
                data = data.encode(UTF8_ENCODING)
            try:
                header, payload = decode_message(data)
                if header != OPAMP_HEADER_NONE:
                    response_msg = _build_error_message(
                        instance_uid=None,
                        error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                        error_message=ERR_UNSUPPORTED_HEADER,
                    )
                else:
                    agent_msg = opamp_pb2.AgentToServer()
                    if payload:
                        agent_msg.ParseFromString(payload)
                    logger.info(LOG_WS_MSG, text_format.MessageToString(agent_msg))
                    client_id = _extract_client_id(agent_msg)

                    if client_id and STORE.is_blocked_agent(client_id):
                        _log_blocked_agent_attempt(
                            client_id=client_id,
                            channel=CHANNEL_WEBSOCKET,
                            headers=ws_headers,
                            remote_addr=remote_addr,
                        )
                        response_msg = _build_error_message(
                            instance_uid=(
                                agent_msg.instance_uid if agent_msg.instance_uid else None
                            ),
                            error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                            error_message=ERR_AGENT_BLOCKED,
                        )
                        close_after_send = True
                    else:
                        known_client = STORE.get(client_id) if client_id else None
                        if provider_config.CONFIG.human_in_loop_approval:
                            if not client_id:
                                response_msg = _build_error_message(
                                    instance_uid=None,
                                    error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                                    error_message=(
                                        "instance_uid is required when "
                                        "human_in_loop_approval is enabled"
                                    ),
                                )
                                close_after_send = True
                            elif known_client is None:
                                if STORE.get_pending_approval(client_id) is None:
                                    try:
                                        STORE.add_pending_approval_from_agent_msg(
                                            agent_msg,
                                            channel=CHANNEL_WEBSOCKET,
                                            remote_addr=remote_addr,
                                        )
                                        logger.info(
                                            "agent moved to pending approval client_id=%s remote_addr=%s",
                                            client_id,
                                            remote_addr or "unknown",
                                        )
                                    except Exception as approval_error:
                                        STORE.block_agent(
                                            client_id,
                                            reason=(
                                                "failed pending approval payload "
                                                f"transformation: {approval_error}"
                                            ),
                                            headers=ws_headers,
                                            ip=remote_addr,
                                        )
                                        logger.exception(
                                            (
                                                "failed to transform pending approval payload; "
                                                "client blocked client_id=%s"
                                            ),
                                            client_id,
                                            exc_info=approval_error,
                                        )
                                        response_msg = _build_error_message(
                                            instance_uid=(
                                                agent_msg.instance_uid
                                                if agent_msg.instance_uid
                                                else None
                                            ),
                                            error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                                            error_message=ERR_AGENT_BLOCKED,
                                        )
                                        close_after_send = True
                                if not close_after_send:
                                    response_msg = _build_error_message(
                                        instance_uid=(
                                            agent_msg.instance_uid
                                            if agent_msg.instance_uid
                                            else None
                                        ),
                                        error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                                        error_message=ERR_AGENT_PENDING_APPROVAL,
                                    )
                                    close_after_send = True

                        if not close_after_send:
                            client = STORE.upsert_from_agent_msg(
                                agent_msg,
                                channel=CHANNEL_WEBSOCKET,
                                remote_addr=remote_addr,
                            )
                            if not _is_heartbeat_only_message(agent_msg):
                                _note_non_heartbeat_state_change_and_maybe_autosave()
                            _WEBSOCKET_CLIENTS[websocket] = client.client_id
                            pending_command = STORE.next_pending_command(client.client_id)
                            response_msg = _build_response(
                                agent_msg,
                                pending_command,
                                client=client,
                                channel=CHANNEL_WEBSOCKET,
                            )
            except ValueError as exc:
                logger.warning("OpAMP websocket value error: %s", exc)
                response_msg = _build_error_message(
                    instance_uid=(
                        agent_msg.instance_uid
                        if "agent_msg" in locals() and agent_msg.instance_uid
                        else None
                    ),
                    error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                    error_message=str(exc),
                )
            except Exception as exc:
                logger.exception("Unhandled websocket error", exc_info=exc)
                response_msg = _build_error_message(
                    instance_uid=(
                        agent_msg.instance_uid
                        if "agent_msg" in locals() and agent_msg.instance_uid
                        else None
                    ),
                    error_type=opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable,
                    error_message="internal server error",
                )

            out_payload = response_msg.SerializeToString()
            await websocket.send(encode_message(out_payload))
            if pending_command is not None and _has_dispatched_command_payload(
                response_msg
            ):
                if client is not None:
                    STORE.mark_command_sent(client.client_id, pending_command)
                    logger.info(
                        LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc)
                    )
            if close_after_send:
                await websocket.close(code=1008)
                break
    finally:
        _WEBSOCKET_CLIENTS.pop(websocket, None)


async def _close_websockets() -> None:
    """Close all active WebSocket connections."""
    if not _WEBSOCKET_CLIENTS:
        return

    async def _close_one(web_socket: object, client_id: str | None) -> None:
        try:
            await web_socket.close(code=1001)
            if client_id:
                logger.info("closed websocket for client %s", client_id)
            else:
                logger.info("closed websocket for unknown client")
        except Exception as err:
            logger.warning(
                "failed to close websocket for client %s - %s", client_id, err
            )

    await asyncio.gather(
        *[
            _close_one(web_socket, client_id)
            for web_socket, client_id in list(_WEBSOCKET_CLIENTS.items())
            if web_socket is not None
        ],
        return_exceptions=True,
    )


@app.after_serving
async def _finalize_server() -> None:
    """Finalizer to cleanly close WebSocket connections on shutdown."""
    await _close_websockets()
    _save_state_snapshot("graceful_shutdown")


@app.get("/api/clients")
async def list_clients() -> Response:
    """List all tracked clients."""
    global _LAST_DISCONNECT_PURGE
    now = datetime.now(timezone.utc)
    keep_minutes = max(1, int(provider_config.CONFIG.minutes_keep_disconnected))
    purge_interval = timedelta(minutes=keep_minutes / 2)
    if _LAST_DISCONNECT_PURGE is None or now - _LAST_DISCONNECT_PURGE >= purge_interval:
        cutoff = now - timedelta(minutes=keep_minutes)
        removed = STORE.purge_disconnected(cutoff)
        if removed:
            logger.info("purged %s disconnected clients", len(removed))
        _LAST_DISCONNECT_PURGE = now
    clients = [client.model_dump(mode=MODEL_DUMP_MODE) for client in STORE.list()]
    return jsonify(
        {
            "clients": clients,
            "total": len(clients),
            "pending_approval_total": STORE.pending_approval_count(),
        }
    )


@app.get("/api/approvals/pending")
async def list_pending_approvals() -> Response:
    """List agents currently waiting for human approval."""
    pending = [
        client.model_dump(mode=MODEL_DUMP_MODE)
        for client in STORE.list_pending_approvals()
    ]
    return jsonify({"clients": pending, "total": len(pending)})


@app.post("/api/approvals/pending")
async def apply_pending_approval_decisions() -> Response:
    """Apply approve/block decisions for pending agents."""
    payload = await request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "payload is required"}), HTTPStatus.BAD_REQUEST
    decisions_raw = payload.get("decisions")
    if not isinstance(decisions_raw, list) or not decisions_raw:
        return jsonify({"error": "decisions array is required"}), HTTPStatus.BAD_REQUEST

    approved = 0
    blocked = 0
    for item in decisions_raw:
        if not isinstance(item, dict):
            continue
        client_id = str(item.get("client_id", "")).strip()
        decision = str(item.get("decision", "")).strip().lower()
        if not client_id:
            continue
        if decision == "approve":
            moved = STORE.approve_pending_approval(client_id)
            if moved is not None:
                approved += 1
            continue
        if decision == "block":
            STORE.block_agent(
                client_id,
                reason="blocked via pending approval workflow",
                headers=_request_header_map(),
                ip=request.remote_addr,
            )
            blocked += 1

    return jsonify(
        {
            "approved": approved,
            "blocked": blocked,
            "pending_approval_total": STORE.pending_approval_count(),
        }
    )


@app.get("/api/commands/custom")
async def list_custom_commands() -> Response:
    """Return custom command metadata for UI command selection/configuration."""
    client_id = (request.args.get("client_id") or "").strip()
    reported_capabilities: set[str] = set()
    if client_id:
        record = STORE.get(client_id)
        if record is not None:
            reported_capabilities = {
                str(capability).strip()
                for capability in record.custom_capabilities_reported
                if str(capability).strip()
            }
    commands = get_command_metadata(
        parameter_exclude_opamp_standard=True,
        custom_only=True,
    )
    for command in commands:
        fqdn = str(command.get("fqdn", "") or "").strip()
        command["reported_by_client"] = bool(fqdn and fqdn in reported_capabilities)
    return jsonify({"commands": commands})


@app.get("/api/clients/<client_id>")
async def get_client(client_id: str) -> Response:
    """Get a single client record."""
    record = STORE.get(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), HTTPStatus.NOT_FOUND
    return jsonify(record.model_dump(mode=MODEL_DUMP_MODE))


@app.delete("/api/clients/<client_id>")
async def delete_client(client_id: str) -> Response:
    """Remove a client from memory."""
    record = STORE.remove_client(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), HTTPStatus.NOT_FOUND
    logger.warning(
        "client removed from store client_id=%s last_state=%s",
        client_id,
        record.model_dump(mode=MODEL_DUMP_MODE),
    )
    return jsonify({"status": "removed"})


@app.post("/api/clients/<client_id>/commands")
async def queue_command(client_id: str) -> Response:
    """Queue a structured command intent for a client."""
    payload = await request.get_json(silent=True)
    logger.debug("queue_command request client_id=%s payload=%s", client_id, payload)
    pairs = None
    if isinstance(payload, list):
        pairs = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("pairs"), list):
            pairs = payload["pairs"]
    if not isinstance(pairs, list) or not pairs:
        return (
            jsonify({"error": "pairs array is required"}),
            HTTPStatus.BAD_REQUEST,
        )
    logger.debug("queue_command parsed pairs client_id=%s pairs=%s", client_id, pairs)

    normalized_pairs: list[dict[str, str]] = []
    values: dict[str, str] = {}
    for pair in pairs:
        if not isinstance(pair, dict) or "key" not in pair or "value" not in pair:
            return (
                jsonify({"error": "each pair must include key and value"}),
                HTTPStatus.BAD_REQUEST,
            )
        key = str(pair["key"]).strip()
        value = str(pair["value"]).strip()
        if not key:
            return (
                jsonify({"error": "pair key cannot be empty"}),
                HTTPStatus.BAD_REQUEST,
            )
        normalized_pairs.append({"key": key, "value": value})
        values[key.lower()] = value

    classifier = values.get("classifier", "").strip().lower()
    operation = values.get("operation", "").strip().lower()
    action = values.get("action", "").strip().lower()
    routing_action = operation or action
    logger.debug(
        "queue_command routing fields client_id=%s classifier=%s operation=%s action=%s routing_action=%s",
        client_id,
        classifier,
        operation,
        action,
        routing_action,
    )
    if classifier not in {
        CLASSIFIER_COMMAND,
        CLASSIFIER_CUSTOM_COMMAND,
        CLASSIFIER_CUSTOM,
    }:
        return (
            jsonify(
                {
                    "error": "classifier must be command, custom, or custom_command",
                    "classifier": classifier,
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    if not routing_action:
        return jsonify({"error": "operation is required"}), HTTPStatus.BAD_REQUEST

    if (classifier, routing_action) not in COMMAND_BUILDERS and (
        classifier,
        "*",
    ) not in COMMAND_BUILDERS:
        logger.debug(
            "queue_command unsupported mapping client_id=%s classifier=%s routing_action=%s builders=%s",
            client_id,
            classifier,
            routing_action,
            sorted(COMMAND_BUILDERS.keys()),
        )
        return (
            jsonify(
                {
                    "error": "unsupported classifier/action",
                    "classifier": classifier,
                    "action": routing_action,
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )

    # Build a command object when a concrete class exists for the operation.
    key_value_dict = {pair["key"]: pair["value"] for pair in normalized_pairs}
    event_description = f"{classifier} {routing_action} command queued"
    if classifier == CLASSIFIER_COMMAND and routing_action == COMMAND_FORCE_RESYNC:
        event_description = "Force Resync"
    command_obj = None
    if (classifier, routing_action) in COMMAND_BUILDERS and (
        (classifier == CLASSIFIER_COMMAND and routing_action == COMMAND_RESTART)
        or (
            classifier == CLASSIFIER_CUSTOM
            and routing_action
            in {COMMAND_CHATOP, COMMAND_SHUTDOWN_AGENT, COMMAND_NULLCOMMAND}
        )
    ):
        logger.debug(
            "queue_command building command object client_id=%s classifier=%s routing_action=%s key_values=%s",
            client_id,
            classifier,
            routing_action,
            key_value_dict,
        )
        command_obj = command_object_factory(
            classifier=classifier,
            key_values=key_value_dict,
        )
        command_obj.set_key_value_dictionary(key_value_dict)
        classifier = command_obj.get_command_classifier()
        routing_action = str(routing_action).strip().lower()
        event_description = command_obj.get_command_description()
        logger.debug(
            "queue_command built command object client_id=%s object_type=%s classifier=%s routing_action=%s",
            client_id,
            command_obj.__class__.__name__,
            classifier,
            routing_action,
        )

    cmd = STORE.queue_command(
        client_id,
        classifier=classifier,
        action=routing_action,
        key_value_pairs=(
            [
                {"key": key_name, "value": key_value}
                for key_name, key_value in command_obj.get_key_value_dictionary().items()
            ]
            if command_obj is not None
            else normalized_pairs
        ),
        event_description=event_description,
        max_events=provider_config.CONFIG.client_event_history_size,
    )
    logger.info(
        LOG_REST_COMMAND,
        client_id,
        cmd.classifier,
        cmd.action,
        cmd.received_at,
    )
    return jsonify(cmd.model_dump(mode=MODEL_DUMP_MODE)), HTTPStatus.CREATED


@app.post("/api/clients/<client_id>/actions")
async def set_client_actions(client_id: str) -> Response:
    """Set next actions for a client."""
    payload = await request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "payload is required"}), HTTPStatus.BAD_REQUEST
    raw_actions = payload.get("actions")
    if raw_actions is None:
        return jsonify({"error": "actions is required"}), HTTPStatus.BAD_REQUEST
    if isinstance(raw_actions, str):
        actions = [raw_actions]
    elif isinstance(raw_actions, list):
        actions = raw_actions
    else:
        return (
            jsonify({"error": "actions must be a list or string"}),
            HTTPStatus.BAD_REQUEST,
        )
    actions = [str(action).strip() for action in actions if str(action).strip()]
    if not actions:
        record = STORE.set_next_actions(client_id, None)
        return jsonify(record.model_dump(mode=MODEL_DUMP_MODE))
    invalid = [action for action in actions if action not in ACTION_OPTIONS]
    if invalid:
        return (
            jsonify(
                {
                    "error": "invalid actions",
                    "invalid": invalid,
                    "allowed": sorted(ACTION_OPTIONS),
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    record = STORE.set_next_actions(client_id, actions)
    return jsonify(record.model_dump(mode=MODEL_DUMP_MODE))


@app.put("/api/clients/<client_id>/heartbeat-frequency")
async def set_client_heartbeat_frequency(client_id: str) -> Response:
    """Set heartbeat frequency for a single client and append an event."""
    payload = await request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "payload is required"}), HTTPStatus.BAD_REQUEST
    try:
        heartbeat_frequency = int(payload.get("heartbeat_frequency"))
    except (TypeError, ValueError):
        return (
            jsonify({"error": "heartbeat_frequency must be an integer"}),
            HTTPStatus.BAD_REQUEST,
        )
    if heartbeat_frequency <= 0:
        return (
            jsonify({"error": "heartbeat_frequency must be positive"}),
            HTTPStatus.BAD_REQUEST,
        )
    record = STORE.set_client_heartbeat_frequency(
        client_id,
        heartbeat_frequency,
        max_events=provider_config.CONFIG.client_event_history_size,
    )
    if record is None:
        return jsonify({"error": "client not found"}), HTTPStatus.NOT_FOUND
    return jsonify(record.model_dump(mode=MODEL_DUMP_MODE))


@app.post("/api/clients/<client_id>/identify")
async def issue_agent_identification(client_id: str) -> Response:
    """Issue a new instance UID for a client."""
    record = STORE.get(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), HTTPStatus.NOT_FOUND
    new_uid = STORE.generate_unique_instance_uid()
    STORE.set_agent_identification(client_id, new_uid)
    STORE.add_event(
        client_id,
        description="Issue New Unique ID",
        max_events=provider_config.CONFIG.client_event_history_size,
    )
    logger.info("issued new instance uid for client %s", client_id)
    return jsonify({"status": "queued", "new_instance_uid": new_uid.hex()})


@app.get("/api/settings/comms")
async def get_comms_settings() -> Response:
    """Get communication threshold settings."""
    state_prefix = pathlib.Path(provider_config.CONFIG.state_persistence.state_file_prefix)
    payload = {
        "delayed_comms_seconds": provider_config.CONFIG.delayed_comms_seconds,
        "significant_comms_seconds": provider_config.CONFIG.significant_comms_seconds,
        "client_event_history_size": provider_config.CONFIG.client_event_history_size,
        "human_in_loop_approval": provider_config.CONFIG.human_in_loop_approval,
        "state_save_folder": str(state_prefix.parent),
        "retention_count": int(
            provider_config.CONFIG.state_persistence.retention_count
        ),
        "state_snapshot_file_count": _state_snapshot_file_count(),
        "autosave_interval_seconds_since_change": int(
            provider_config.CONFIG.state_persistence.autosave_interval_seconds_since_change
        ),
    }
    payload.update(_tls_certificate_expiry_metadata())
    return jsonify(payload)


@app.get("/api/settings/diagnostic")
async def get_diagnostic_settings() -> Response:
    """Return diagnostic-mode status used by UI feature gating."""
    return jsonify(
        {
            "diagnostic_enabled": _diagnostic_mode_enabled(),
            "state_persistence_enabled": provider_config.CONFIG.state_persistence.enabled
            is True,
            "state_persistence": dict(_PERSISTENCE_STATUS),
        }
    )


@app.post("/api/settings/state/save")
async def save_state_snapshot_now() -> Response:
    """Force an immediate persisted-state snapshot save."""
    persistence = provider_config.CONFIG.state_persistence
    if persistence.enabled is not True:
        _record_snapshot_status(
            status="skipped",
            path=None,
            reason="manual_ui_trigger_disabled",
        )
        return (
            jsonify({"error": "state persistence is disabled"}),
            HTTPStatus.BAD_REQUEST,
        )
    now = datetime.now(timezone.utc)
    try:
        path = save_state_snapshot(
            store=STORE,
            persistence=persistence,
            reason="manual_ui_trigger",
            logger=logger,
            now=now,
        )
        snapshot_path = str(path) if path is not None else None
        _record_snapshot_status(
            status="saved",
            path=snapshot_path,
            reason="manual_ui_trigger",
            at=now,
        )
        return jsonify(
            {
                "status": "saved",
                "snapshot_path": snapshot_path,
                "saved_at_utc": now.replace(microsecond=0).isoformat(),
            }
        )
    except Exception as exc:
        logger.exception(
            "manual state snapshot save failed",
            exc_info=exc,
        )
        _record_snapshot_status(
            status="failed",
            path=None,
            reason="manual_ui_trigger",
            at=now,
        )
        return (
            jsonify({"error": "failed to save provider state snapshot"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@app.get("/api/settings/server-opamp-config")
async def get_server_opamp_config() -> Response:
    """Return provider config file content for diagnostic UI view."""
    if not _diagnostic_mode_enabled():
        return (
            jsonify({"error": "diagnostic mode is disabled"}),
            HTTPStatus.FORBIDDEN,
        )

    config_path = provider_config.get_effective_config_path().resolve()
    if not config_path.exists() or not config_path.is_file():
        return (
            jsonify({"error": "provider config file not found"}),
            HTTPStatus.NOT_FOUND,
        )
    if config_path.suffix.lower() != ".json":
        return (
            jsonify({"error": "provider config path must be a JSON file"}),
            HTTPStatus.BAD_REQUEST,
        )

    try:
        config_raw = config_path.read_text(encoding=UTF8_ENCODING)
        config_json = json.loads(config_raw)
    except Exception as exc:
        logger.exception("failed to read provider config file", exc_info=exc)
        return (
            jsonify({"error": "failed to read provider config file"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    return jsonify(
        {
            "diagnostic_enabled": True,
            "config_path": str(config_path),
            "config_text": json.dumps(config_json, indent=2),
        }
    )


@app.put("/api/settings/comms")
async def update_comms_settings() -> Response:
    """Update communication threshold settings."""
    payload = await request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "payload is required"}), HTTPStatus.BAD_REQUEST
    try:
        delayed = int(
            payload.get(
                "delayed_comms_seconds", provider_config.CONFIG.delayed_comms_seconds
            )
        )
        significant = int(
            payload.get(
                "significant_comms_seconds",
                provider_config.CONFIG.significant_comms_seconds,
            )
        )
        client_event_history_size = int(
            payload.get(
                "client_event_history_size",
                provider_config.CONFIG.client_event_history_size,
            )
        )
        human_in_loop_approval = _coerce_bool_setting(
            payload.get(
                "human_in_loop_approval",
                provider_config.CONFIG.human_in_loop_approval,
            ),
            key="human_in_loop_approval",
        )
        state_save_folder = str(
            payload.get(
                "state_save_folder",
                str(
                    pathlib.Path(
                        provider_config.CONFIG.state_persistence.state_file_prefix
                    ).parent
                ),
            )
        ).strip()
        autosave_interval_seconds_since_change = int(
            payload.get(
                "autosave_interval_seconds_since_change",
                provider_config.CONFIG.state_persistence.autosave_interval_seconds_since_change,
            )
        )
        retention_count = int(
            payload.get(
                "retention_count",
                provider_config.CONFIG.state_persistence.retention_count,
            )
        )
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "error": (
                        "thresholds must be integers, "
                        "human_in_loop_approval must be boolean, and "
                        "autosave_interval_seconds_since_change/retention_count must be integer"
                    )
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    if delayed <= 0 or significant <= 0 or client_event_history_size <= 0:
        return jsonify({"error": "thresholds must be positive"}), HTTPStatus.BAD_REQUEST
    if autosave_interval_seconds_since_change <= 0:
        return (
            jsonify(
                {
                    "error": (
                        "autosave_interval_seconds_since_change must be a positive integer"
                    )
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    if retention_count <= 0:
        return (
            jsonify(
                {
                    "error": "retention_count must be a positive integer"
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    if not state_save_folder:
        return (
            jsonify({"error": "state_save_folder must be a non-empty string"}),
            HTTPStatus.BAD_REQUEST,
        )
    if delayed >= significant:
        return (
            jsonify({"error": "significant must be greater than delayed"}),
            HTTPStatus.BAD_REQUEST,
        )
    try:
        config = provider_config.update_comms_thresholds(
            delayed=delayed,
            significant=significant,
            client_event_history_size=client_event_history_size,
            human_in_loop_approval=human_in_loop_approval,
            state_save_folder=state_save_folder,
            retention_count=retention_count,
            autosave_interval_seconds_since_change=(
                autosave_interval_seconds_since_change
            ),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
    try:
        if retention_count < _state_snapshot_file_count():
            prune_snapshot_files(
                state_file_prefix=config.state_persistence.state_file_prefix,
                retention_count=config.state_persistence.retention_count,
                logger=logger,
            )
    except Exception as exc:
        logger.warning(
            "failed pruning snapshots after retention update",
            exc_info=exc,
        )
    try:
        provider_config.persist_provider_config(config)
    except Exception as exc:
        logger.exception("failed to persist provider settings", exc_info=exc)
        return (
            jsonify({"error": "failed to persist provider settings to opamp.json"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    return jsonify(
        {
            "delayed_comms_seconds": config.delayed_comms_seconds,
            "significant_comms_seconds": config.significant_comms_seconds,
            "client_event_history_size": config.client_event_history_size,
            "human_in_loop_approval": config.human_in_loop_approval,
            "state_save_folder": str(
                pathlib.Path(config.state_persistence.state_file_prefix).parent
            ),
            "retention_count": int(config.state_persistence.retention_count),
            "state_snapshot_file_count": _state_snapshot_file_count(),
            "autosave_interval_seconds_since_change": int(
                config.state_persistence.autosave_interval_seconds_since_change
            ),
        }
    )


@app.get("/api/settings/client")
async def get_client_settings() -> Response:
    """Get client global settings."""
    return jsonify(
        {
            "default_heartbeat_frequency": STORE.get_default_heartbeat_frequency(),
        }
    )


@app.put("/api/settings/client")
async def update_client_settings() -> Response:
    """Update client global settings and apply to all known clients."""
    payload = await request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "payload is required"}), HTTPStatus.BAD_REQUEST
    try:
        default_heartbeat_frequency = int(
            payload.get(
                "default_heartbeat_frequency",
                STORE.get_default_heartbeat_frequency(),
            )
        )
    except (TypeError, ValueError):
        return (
            jsonify({"error": "default_heartbeat_frequency must be an integer"}),
            HTTPStatus.BAD_REQUEST,
        )
    if default_heartbeat_frequency <= 0:
        return (
            jsonify({"error": "default_heartbeat_frequency must be positive"}),
            HTTPStatus.BAD_REQUEST,
        )
    config = provider_config.update_default_heartbeat_frequency(
        default_heartbeat_frequency=default_heartbeat_frequency
    )
    try:
        provider_config.persist_provider_config(config)
    except Exception as exc:
        logger.exception("failed to persist provider settings", exc_info=exc)
        return (
            jsonify({"error": "failed to persist provider settings to opamp.json"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    updated_clients = STORE.set_default_heartbeat_frequency(
        default_heartbeat_frequency,
        max_events=provider_config.CONFIG.client_event_history_size,
    )
    return jsonify(
        {
            "default_heartbeat_frequency": STORE.get_default_heartbeat_frequency(),
            "updated_clients": updated_clients,
        }
    )


@app.post("/api/clients/<client_id>/config")
async def set_requested_config(client_id: str) -> Response:
    """Set requested configuration for a client."""
    payload = await request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "payload is required"}), HTTPStatus.BAD_REQUEST
    config_text = str(payload.get("config", "")).strip()
    if not config_text:
        return jsonify({"error": "config is required"}), HTTPStatus.BAD_REQUEST
    version = payload.get("version")
    apply_at_raw = payload.get("apply_at")
    apply_at = None
    if apply_at_raw:
        try:
            apply_at = datetime.fromisoformat(str(apply_at_raw))
        except ValueError:
            return (
                jsonify({"error": "apply_at must be ISO 8601"}),
                HTTPStatus.BAD_REQUEST,
            )
    record = STORE.set_requested_config(
        client_id,
        config_text=config_text,
        version=str(version) if version else None,
        apply_at=apply_at,
    )
    return jsonify(record.model_dump(mode=MODEL_DUMP_MODE))


@app.get("/")
async def root() -> Response:
    return redirect("/ui")


@app.get("/ui")
async def web_ui() -> Response:
    """Serve the provider web UI."""
    html = _WEB_UI_HTML
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/web_ui.css")
async def web_ui_css() -> Response:
    """Serve the provider web UI stylesheet."""
    return Response(
        _WEB_UI_CSS,
        content_type="text/css; charset=utf-8",
    )


@app.get("/web_ui_state.js")
async def web_ui_state_js() -> Response:
    """Serve the provider web UI state/bootstrap JavaScript."""
    return Response(
        _WEB_UI_STATE_JS,
        content_type="application/javascript; charset=utf-8",
    )


@app.get("/web_ui_functions.js")
async def web_ui_functions_js() -> Response:
    """Serve the provider web UI function library JavaScript."""
    return Response(
        _WEB_UI_FUNCTIONS_JS,
        content_type="application/javascript; charset=utf-8",
    )


@app.get("/web_ui_bindings.js")
async def web_ui_bindings_js() -> Response:
    """Serve the provider web UI event-binding JavaScript."""
    return Response(
        _WEB_UI_BINDINGS_JS,
        content_type="application/javascript; charset=utf-8",
    )


@app.get("/help")
async def help_page() -> Response:
    """Serve a simple help page."""
    html = (
        _HELP_HTML.replace(
            "__DELAYED_SECONDS__", str(provider_config.CONFIG.delayed_comms_seconds)
        )
        .replace(
            "__SIGNIFICANT_SECONDS__",
            str(provider_config.CONFIG.significant_comms_seconds),
        )
        .replace(
            "__HELP_DELAYED_COMMS_SECONDS__",
            GLOBAL_SETTINGS_HELP["delayed_comms_seconds"]["tooltip"],
        )
        .replace(
            "__HELP_SIGNIFICANT_COMMS_SECONDS__",
            GLOBAL_SETTINGS_HELP["significant_comms_seconds"]["tooltip"],
        )
        .replace(
            "__HELP_CLIENT_EVENT_HISTORY_SIZE__",
            GLOBAL_SETTINGS_HELP["client_event_history_size"]["tooltip"],
        )
        .replace(
            "__HELP_HUMAN_IN_LOOP_APPROVAL__",
            GLOBAL_SETTINGS_HELP["human_in_loop_approval"]["tooltip"],
        )
        .replace(
            "__HELP_STATE_SAVE_FOLDER__",
            GLOBAL_SETTINGS_HELP["state_save_folder"]["tooltip"],
        )
        .replace(
            "__HELP_RETENTION_COUNT__",
            GLOBAL_SETTINGS_HELP["retention_count"]["tooltip"],
        )
        .replace(
            "__HELP_AUTOSAVE_INTERVAL_SECONDS_SINCE_CHANGE__",
            GLOBAL_SETTINGS_HELP["autosave_interval_seconds_since_change"]["tooltip"],
        )
        .replace(
            "__HELP_DEFAULT_HEARTBEAT_FREQUENCY__",
            GLOBAL_SETTINGS_HELP["default_heartbeat_frequency"]["tooltip"],
        )
    )
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/api/help/global-settings")
async def global_settings_help() -> Response:
    """Return shared help text used by global settings tooltips and help page."""
    tooltips = {
        key: value.get("tooltip", "") for key, value in GLOBAL_SETTINGS_HELP.items()
    }
    return jsonify({"fields": GLOBAL_SETTINGS_HELP, "tooltips": tooltips})


@app.get("/create.ico")
async def favicon() -> Response:
    """Serve the UI favicon."""
    return Response(
        _ICON_PATH.read_bytes(),
        content_type="image/x-icon",
    )


@app.post("/api/shutdown")
async def shutdown_server() -> Response:
    """Shutdown the server if explicitly confirmed."""
    payload = await request.get_json(silent=True) or {}
    confirm = payload.get("confirm") is True
    if not confirm:
        return jsonify({"error": "confirm is required"}), HTTPStatus.BAD_REQUEST
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    logger.warning("shutdown requested via API")
    await _close_websockets()
    asyncio.create_task(_shutdown_after_response())
    return jsonify({"status": "shutting down"})


_HTML_DIR = pathlib.Path(__file__).with_name("html")
_WEB_UI_PATH = _HTML_DIR / "web_ui.html"
_WEB_UI_HTML = _WEB_UI_PATH.read_text(encoding=UTF8_ENCODING)
_WEB_UI_CSS_PATH = _HTML_DIR / "web_ui.css"
_WEB_UI_CSS = _WEB_UI_CSS_PATH.read_text(encoding=UTF8_ENCODING)
_WEB_UI_STATE_JS_PATH = _HTML_DIR / "web_ui_state.js"
_WEB_UI_STATE_JS = _WEB_UI_STATE_JS_PATH.read_text(encoding=UTF8_ENCODING)
_WEB_UI_FUNCTIONS_JS_PATH = _HTML_DIR / "web_ui_functions.js"
_WEB_UI_FUNCTIONS_JS = _WEB_UI_FUNCTIONS_JS_PATH.read_text(encoding=UTF8_ENCODING)
_WEB_UI_BINDINGS_JS_PATH = _HTML_DIR / "web_ui_bindings.js"
_WEB_UI_BINDINGS_JS = _WEB_UI_BINDINGS_JS_PATH.read_text(encoding=UTF8_ENCODING)

_HELP_PATH = _HTML_DIR / "help.html"
_HELP_HTML = _HELP_PATH.read_text(encoding=UTF8_ENCODING)

_ICON_PATH = _HTML_DIR / "create.ico"
