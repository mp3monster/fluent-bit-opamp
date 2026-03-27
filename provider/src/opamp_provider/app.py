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

app = Quart(__name__)
register_tool_routes(app)
register_mcp_transport(app)
logger = logging.getLogger(__name__)
tracemalloc.start()

CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
LOG_HTTP_MSG = "opamp http AgentToServer:\n%s"  # Log format for HTTP messages.
LOG_WS_MSG = "opamp ws AgentToServer:\n%s"  # Log format for WebSocket messages.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
LOG_REST_COMMAND = "queued command for client %s classifier=%s action=%s at %s"
LOG_SEND_COMMAND = "sent command to client %s at %s"
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.
SERVER_CAPABILITIES = int(
    ServerCapabilities.AcceptsStatus
)  # Server advertises AcceptsStatus only.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
MODEL_DUMP_MODE = "json"

COMMAND_RESTART = "restart"
COMMAND_FORCE_RESYNC = "forceresync"
COMMAND_CHATOP = "chatopcommand"
COMMAND_SHUTDOWN_AGENT = "shutdownagent"
COMMAND_NULLCOMMAND = "nullcommand"
CLASSIFIER_COMMAND = "command"
CLASSIFIER_CUSTOM_COMMAND = "custom_command"
CLASSIFIER_CUSTOM = "custom"
CHANNEL_HTTP = "HTTP"
CHANNEL_WEBSOCKET = "websocket"
ACTION_APPLY_CONFIG = "apply_config"
ACTION_CHANGE_CONNECTIONS = "change_connections"
ACTION_PACKAGE_AVAILABLE = "package_availabe"
ACTION_COMMAND_AGENT = "command_agent"
ACTION_CUSTOM_AGENT_COMMAND = "custom_agent_command"
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
    "default_heartbeat_frequency": {
        "label": "Default Heartbeat Frequency (seconds)",
        "tooltip": (
            "Default heartbeat interval in seconds applied to clients when globally updated."
        ),
    },
}
_SHUTDOWN_REQUESTED = False
_LAST_DISCONNECT_PURGE: datetime | None = None
_WEBSOCKET_CLIENTS: dict[object, str | None] = {}

# Keep in-memory client heartbeat defaults aligned with loaded provider config.
STORE.set_default_heartbeat_frequency(
    provider_config.CONFIG.default_heartbeat_frequency,
    max_events=provider_config.CONFIG.client_event_history_size,
)


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
        client = STORE.upsert_from_agent_msg(agent_msg, channel=CHANNEL_HTTP)
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
        response_msg = _build_error(
            opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable,
            "internal server error",
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
    try:
        while True:
            pending_command = None
            data = await websocket.receive()
            if isinstance(data, str):
                data = data.encode(UTF8_ENCODING)
            try:
                header, payload = decode_message(data)
                if header != OPAMP_HEADER_NONE:
                    response_msg = _build_error(
                        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                        ERR_UNSUPPORTED_HEADER,
                        agent_msg.instance_uid if "agent_msg" in locals() else None,
                    )
                else:
                    agent_msg = opamp_pb2.AgentToServer()
                    if payload:
                        agent_msg.ParseFromString(payload)
                    logger.info(LOG_WS_MSG, text_format.MessageToString(agent_msg))
                    client = STORE.upsert_from_agent_msg(
                        agent_msg, channel=CHANNEL_WEBSOCKET
                    )
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
                response_msg = _build_error(
                    opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest,
                    str(exc),
                    agent_msg.instance_uid if "agent_msg" in locals() else None,
                )
            except Exception as exc:
                logger.exception("Unhandled websocket error", exc_info=exc)
                response_msg = _build_error(
                    opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_Unavailable,
                    "internal server error",
                    agent_msg.instance_uid if "agent_msg" in locals() else None,
                )

            out_payload = response_msg.SerializeToString()
            await websocket.send(encode_message(out_payload))
            if pending_command is not None and _has_dispatched_command_payload(
                response_msg
            ):
                STORE.mark_command_sent(client.client_id, pending_command)
                logger.info(
                    LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc)
                )
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
    return jsonify({"clients": clients, "total": len(clients)})


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
        elif "command" in payload:
            legacy_action = str(payload["command"]).strip()
            pairs = [
                {"key": "classifier", "value": CLASSIFIER_COMMAND},
                {"key": "action", "value": legacy_action},
            ]
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
    logger.info("issued new instance uid for client %s", client_id)
    return jsonify({"status": "queued", "new_instance_uid": new_uid.hex()})


@app.get("/api/settings/comms")
async def get_comms_settings() -> Response:
    """Get communication threshold settings."""
    return jsonify(
        {
            "delayed_comms_seconds": provider_config.CONFIG.delayed_comms_seconds,
            "significant_comms_seconds": provider_config.CONFIG.significant_comms_seconds,
            "client_event_history_size": provider_config.CONFIG.client_event_history_size,
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
    except (TypeError, ValueError):
        return jsonify({"error": "thresholds must be integers"}), HTTPStatus.BAD_REQUEST
    if delayed <= 0 or significant <= 0 or client_event_history_size <= 0:
        return jsonify({"error": "thresholds must be positive"}), HTTPStatus.BAD_REQUEST
    if delayed >= significant:
        return (
            jsonify({"error": "significant must be greater than delayed"}),
            HTTPStatus.BAD_REQUEST,
        )
    config = provider_config.update_comms_thresholds(
        delayed=delayed,
        significant=significant,
        client_event_history_size=client_event_history_size,
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

_HELP_PATH = _HTML_DIR / "help.html"
_HELP_HTML = _HELP_PATH.read_text(encoding=UTF8_ENCODING)

_ICON_PATH = _HTML_DIR / "create.ico"
