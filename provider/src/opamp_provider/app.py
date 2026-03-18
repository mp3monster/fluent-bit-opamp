"""Quart OpAMP server skeleton."""

from __future__ import annotations

import asyncio
from typing import Set
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
from opamp_provider.config import CONFIG
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import STORE, CommandRecord
from opamp_provider.transport import decode_message, encode_message
from shared.opamp_config import (
    OPAMP_HTTP_PATH,
    OPAMP_TRANSPORT_HEADER_NONE,
    UTF8_ENCODING,
)

app = Quart(__name__)
logger = logging.getLogger(__name__)
tracemalloc.start()

CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
LOG_HTTP_MSG = "opamp http AgentToServer:\n%s"  # Log format for HTTP messages.
LOG_WS_MSG = "opamp ws AgentToServer:\n%s"  # Log format for WebSocket messages.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
LOG_REST_COMMAND = "queued command for client %s at %s"
LOG_SEND_COMMAND = "sent command to client %s at %s"
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.

COMMAND_RESTART = "restart"
CHANNEL_HTTP = "HTTP"
CHANNEL_WEBSOCKET = "WebSocket"
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
_SHUTDOWN_REQUESTED = False
_LAST_DISCONNECT_PURGE: datetime | None = None
_WEBSOCKET_CLIENTS: dict[object, str | None] = {}


def _request_process_shutdown() -> None:
    try:
        os.kill(os.getpid(), signal.SIGINT)
    except Exception:
        os._exit(0)


async def _shutdown_after_response() -> None:
    await asyncio.sleep(0.2)
    _request_process_shutdown()


@app.errorhandler(Exception)
async def handle_unexpected_error(error: Exception) -> Response:
    if isinstance(error, HTTPException):
        return error
    logger.exception("Unhandled app error", exc_info=error)
    return jsonify({"error": "internal server error"}), HTTPStatus.INTERNAL_SERVER_ERROR


def _build_apply_config(response: opamp_pb2.ServerToAgent) -> opamp_pb2.ServerToAgent:
    logger.info("building next action payload: %s", ACTION_APPLY_CONFIG)
    response.remote_config.SetInParent()
    return response


def _build_change_connections(
    response: opamp_pb2.ServerToAgent,
) -> opamp_pb2.ServerToAgent:
    logger.info("building next action payload: %s", ACTION_CHANGE_CONNECTIONS)
    response.connection_settings.SetInParent()
    return response


def _build_package_available(
    response: opamp_pb2.ServerToAgent,
) -> opamp_pb2.ServerToAgent:
    logger.info("building next action payload: %s", ACTION_PACKAGE_AVAILABLE)
    response.packages_available.SetInParent()
    return response


def _build_command_agent(
    response: opamp_pb2.ServerToAgent, pending_command: CommandRecord | None
) -> opamp_pb2.ServerToAgent:
    logger.info("building next action payload: %s", ACTION_COMMAND_AGENT)
    if (
        pending_command is not None
        and pending_command.command.lower() == COMMAND_RESTART
    ):
        response.command.type = opamp_pb2.CommandType.CommandType_Restart
    else:
        response.command.SetInParent()
    return response


def _build_custom_agent_command(
    response: opamp_pb2.ServerToAgent,
) -> opamp_pb2.ServerToAgent:
    logger.info("building next action payload: %s", ACTION_CUSTOM_AGENT_COMMAND)
    response.custom_message.SetInParent()
    return response


def _apply_next_action(
    response: opamp_pb2.ServerToAgent,
    *,
    action: str,
    pending_command: CommandRecord | None,
) -> opamp_pb2.ServerToAgent:
    if action == ACTION_APPLY_CONFIG:
        return _build_apply_config(response)
    if action == ACTION_CHANGE_CONNECTIONS:
        return _build_change_connections(response)
    if action == ACTION_PACKAGE_AVAILABLE:
        return _build_package_available(response)
    if action == ACTION_COMMAND_AGENT:
        return _build_command_agent(response, pending_command)
    if action == ACTION_CUSTOM_AGENT_COMMAND:
        return _build_custom_agent_command(response)
    logger.warning("unknown next action: %s", action)
    return response


def _build_response(
    request_msg: opamp_pb2.AgentToServer,
    pending_command: CommandRecord | None,
    client_id: str | None = None,
    channel: str | None = None,
) -> opamp_pb2.ServerToAgent:
    """Build a minimal ServerToAgent response for a request."""
    response = opamp_pb2.ServerToAgent()
    if request_msg.instance_uid:
        response.instance_uid = request_msg.instance_uid
        logger.info("set response to: %s", response.instance_uid)
    else:
        logger.warning("Cant set response instance_uid")

    # Capabilities are read from config/opamp.json at startup.
    response.capabilities = CONFIG.server_capabilities
    if client_id:
        pending_identification = STORE.pop_agent_identification(client_id)
        if pending_identification:
            response.agent_identification.new_instance_uid = pending_identification
    # TODO(opamp): Implement operations that respond to AgentToServer fields:
    # - remote config offers (AgentRemoteConfig)
    # - connection settings offers (ConnectionSettingsOffers)
    # - packages available (PackagesAvailable)
    # - commands (ServerToAgentCommand)
    # - custom capabilities and custom messages
    # - instance UID reassignment (AgentIdentification)
    if channel == CHANNEL_HTTP and client_id:
        next_action = STORE.pop_next_action(client_id)
        if next_action:
            response = _apply_next_action(
                response, action=next_action, pending_command=pending_command
            )
    if pending_command is not None and not response.HasField("command"):
        if pending_command.command.lower() == COMMAND_RESTART:
            response.command.type = opamp_pb2.CommandType.CommandType_Restart
    return response


def _build_error(
    message: str, instance_uid: bytes | None = None
) -> opamp_pb2.ServerToAgent:
    """Build a ServerToAgent error response."""
    response = opamp_pb2.ServerToAgent()
    if instance_uid:
        response.instance_uid = instance_uid
    response.error_response.type = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    )
    response.error_response.error_message = message
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
        client = STORE.upsert_from_agent_msg(agent_msg, channel=CHANNEL_HTTP)
        pending_command = STORE.next_pending_command(client.client_id)

        # TODO(opamp): Implement per-operation processing for HTTP transport:
        # - status/health updates
        # - effective config reporting
        # - remote config status
        # - package statuses
        # - connection settings requests and status
        # - custom messages
        response_msg = _build_response(
            agent_msg,
            pending_command,
            client.client_id,
            channel=CHANNEL_HTTP,
        )
        payload = response_msg.SerializeToString()
        if pending_command is not None and response_msg.HasField("command"):
            STORE.mark_command_sent(client.client_id, pending_command)
            logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))
        return Response(payload, content_type=CONTENT_TYPE_PROTO)
    except Exception as exc:
        logger.exception("Unhandled HTTP error", exc_info=exc)
        response_msg = _build_error("internal server error")
        payload = response_msg.SerializeToString()
        return Response(
            payload,
            content_type=CONTENT_TYPE_PROTO,
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@app.websocket(OPAMP_HTTP_PATH)
async def opamp_ws() -> None:
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
                    # TODO(opamp): Implement per-operation processing for WebSocket transport:
                    # - status/health updates
                    # - effective config reporting
                    # - remote config status
                    # - package statuses
                    # - connection settings requests and status
                    # - custom messages
                    response_msg = _build_response(
                        agent_msg,
                        pending_command,
                        client.client_id,
                        channel=CHANNEL_WEBSOCKET,
                    )
            except ValueError as exc:
                logger.warning("OpAMP websocket value error: %s", exc)
                response_msg = _build_error(
                    str(exc),
                    agent_msg.instance_uid if "agent_msg" in locals() else None,
                )
            except Exception as exc:
                logger.exception("Unhandled websocket error", exc_info=exc)
                response_msg = _build_error(
                    "internal server error",
                    agent_msg.instance_uid if "agent_msg" in locals() else None,
                )

            out_payload = response_msg.SerializeToString()
            await websocket.send(encode_message(out_payload))
            if response_msg.HasField("command"):
                STORE.mark_command_sent(client.client_id, pending_command)
                logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))
    finally:
        _WEBSOCKET_CLIENTS.pop(websocket, None)


async def _close_websockets() -> None:
    """Close all active WebSocket connections."""
    if not _WEBSOCKET_CLIENTS:
        return
    async def _close_one(ws: object, client_id: str | None) -> None:
        try:
            await ws.close(code=1001)
            if client_id:
                logger.info("closed websocket for client %s", client_id)
            else:
                logger.info("closed websocket for unknown client")
        except Exception:
            logger.warning("failed to close websocket for client %s", client_id)

    await asyncio.gather(
        *[
            _close_one(ws, client_id)
            for ws, client_id in list(_WEBSOCKET_CLIENTS.items())
            if ws is not None
        ],
        return_exceptions=True,
    )


@app.get("/api/clients")
async def list_clients() -> Response:
    """List all tracked clients."""
    global _LAST_DISCONNECT_PURGE
    now = datetime.now(timezone.utc)
    keep_minutes = max(1, int(CONFIG.minutes_keep_disconnected))
    purge_interval = timedelta(minutes=keep_minutes / 2)
    if _LAST_DISCONNECT_PURGE is None or now - _LAST_DISCONNECT_PURGE >= purge_interval:
        cutoff = now - timedelta(minutes=keep_minutes)
        removed = STORE.purge_disconnected(cutoff)
        if removed:
            logger.info("purged %s disconnected clients", len(removed))
        _LAST_DISCONNECT_PURGE = now
    clients = [client.model_dump(mode="json") for client in STORE.list()]
    return jsonify({"clients": clients, "total": len(clients)})


@app.get("/api/clients/<client_id>")
async def get_client(client_id: str) -> Response:
    """Get a single client record."""
    record = STORE.get(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), HTTPStatus.NOT_FOUND
    return jsonify(record.model_dump(mode="json"))


@app.delete("/api/clients/<client_id>")
async def delete_client(client_id: str) -> Response:
    """Remove a client from memory."""
    record = STORE.remove_client(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), HTTPStatus.NOT_FOUND
    logger.warning(
        "client removed from store client_id=%s last_state=%s",
        client_id,
        record.model_dump(mode="json"),
    )
    return jsonify({"status": "removed"})


@app.post("/api/clients/<client_id>/commands")
async def queue_command(client_id: str) -> Response:
    """Queue a command for a client."""
    payload = await request.get_json(silent=True)
    if not payload or "command" not in payload:
        return jsonify({"error": "command is required"}), HTTPStatus.BAD_REQUEST
    command = str(payload["command"]).strip()
    if not command:
        return jsonify({"error": "command is required"}), HTTPStatus.BAD_REQUEST
    cmd = STORE.queue_command(client_id, command)
    logger.info(LOG_REST_COMMAND, client_id, cmd.received_at)
    return jsonify(cmd.model_dump(mode="json")), HTTPStatus.CREATED


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
        return jsonify({"error": "actions must be a list or string"}), HTTPStatus.BAD_REQUEST
    actions = [str(action).strip() for action in actions if str(action).strip()]
    if not actions:
        record = STORE.set_next_actions(client_id, None)
        return jsonify(record.model_dump(mode="json"))
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
    return jsonify(record.model_dump(mode="json"))


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
            "delayed_comms_seconds": CONFIG.delayed_comms_seconds,
            "significant_comms_seconds": CONFIG.significant_comms_seconds,
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
            payload.get("delayed_comms_seconds", CONFIG.delayed_comms_seconds)
        )
        significant = int(
            payload.get("significant_comms_seconds", CONFIG.significant_comms_seconds)
        )
    except (TypeError, ValueError):
        return jsonify({"error": "thresholds must be integers"}), HTTPStatus.BAD_REQUEST
    if delayed <= 0 or significant <= 0:
        return jsonify({"error": "thresholds must be positive"}), HTTPStatus.BAD_REQUEST
    if delayed >= significant:
        return (
            jsonify({"error": "significant must be greater than delayed"}),
            HTTPStatus.BAD_REQUEST,
        )
    config = provider_config.update_comms_thresholds(
        delayed=delayed,
        significant=significant,
    )
    return jsonify(
        {
            "delayed_comms_seconds": config.delayed_comms_seconds,
            "significant_comms_seconds": config.significant_comms_seconds,
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
    return jsonify(record.model_dump(mode="json"))


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
    html = _HELP_HTML.replace(
        "__DELAYED_SECONDS__", str(CONFIG.delayed_comms_seconds)
    ).replace("__SIGNIFICANT_SECONDS__", str(CONFIG.significant_comms_seconds))
    return Response(html, content_type="text/html; charset=utf-8")


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


_WEB_UI_PATH = pathlib.Path(__file__).with_name("web_ui.html")
_WEB_UI_HTML = _WEB_UI_PATH.read_text(encoding=UTF8_ENCODING)

_HELP_PATH = pathlib.Path(__file__).with_name("help.html")
_HELP_HTML = _HELP_PATH.read_text(encoding=UTF8_ENCODING)
