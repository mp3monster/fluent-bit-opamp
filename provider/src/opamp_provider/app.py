"""Quart OpAMP server skeleton."""

from __future__ import annotations

import logging
import pathlib
import tracemalloc
from datetime import datetime, timezone

from google.protobuf import text_format
from quart import Quart, Response, jsonify, redirect, request, websocket

from opamp_provider import config as provider_config
from opamp_provider.config import CONFIG
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import STORE, CommandRecord
from opamp_provider.transport import decode_message, encode_message
from shared.opamp_config import OPAMP_HTTP_PATH, OPAMP_TRANSPORT_HEADER_NONE, UTF8_ENCODING

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


def _build_response(
    request_msg: opamp_pb2.AgentToServer,
    pending_command: CommandRecord | None,
) -> opamp_pb2.ServerToAgent:
    """Build a minimal ServerToAgent response for a request."""
    response = opamp_pb2.ServerToAgent()
    response.instance_uid = request_msg.instance_uid
    # Capabilities are read from config/opamp.json at startup.
    response.capabilities = CONFIG.server_capabilities
    # TODO(opamp): Implement operations that respond to AgentToServer fields:
    # - remote config offers (AgentRemoteConfig)
    # - connection settings offers (ConnectionSettingsOffers)
    # - packages available (PackagesAvailable)
    # - commands (ServerToAgentCommand)
    # - custom capabilities and custom messages
    # - instance UID reassignment (AgentIdentification)
    if pending_command is not None:
        if pending_command.command.lower() == COMMAND_RESTART:
            response.command.type = opamp_pb2.CommandType.CommandType_Restart
    return response


def _build_error(message: str) -> opamp_pb2.ServerToAgent:
    """Build a ServerToAgent error response."""
    response = opamp_pb2.ServerToAgent()
    response.error_response.type = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    )
    response.error_response.error_message = message
    return response


@app.post(OPAMP_HTTP_PATH)
async def opamp_http() -> Response:
    """Handle OpAMP HTTP POST requests."""
    data = await request.get_data()
    agent_msg = opamp_pb2.AgentToServer()
    if data:
        agent_msg.ParseFromString(data)

    logger.info(LOG_HTTP_MSG, text_format.MessageToString(agent_msg))
    client = STORE.upsert_from_agent_msg(agent_msg)
    pending_command = STORE.next_pending_command(client.client_id)

    # TODO(opamp): Implement per-operation processing for HTTP transport:
    # - status/health updates
    # - effective config reporting
    # - remote config status
    # - package statuses
    # - connection settings requests and status
    # - custom messages
    response_msg = _build_response(agent_msg, pending_command)
    payload = response_msg.SerializeToString()
    if pending_command is not None and response_msg.HasField("command"):
        STORE.mark_command_sent(client.client_id, pending_command)
        logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))
    return Response(payload, content_type=CONTENT_TYPE_PROTO)


@app.websocket(OPAMP_HTTP_PATH)
async def opamp_ws() -> None:
    """Handle OpAMP WebSocket connections."""
    while True:
        data = await websocket.receive()
        if isinstance(data, str):
            data = data.encode(UTF8_ENCODING)
        try:
            header, payload = decode_message(data)
            if header != OPAMP_HEADER_NONE:
                response_msg = _build_error(ERR_UNSUPPORTED_HEADER)
            else:
                agent_msg = opamp_pb2.AgentToServer()
                if payload:
                    agent_msg.ParseFromString(payload)
                logger.info(LOG_WS_MSG, text_format.MessageToString(agent_msg))
                client = STORE.upsert_from_agent_msg(agent_msg)
                pending_command = STORE.next_pending_command(client.client_id)
                # TODO(opamp): Implement per-operation processing for WebSocket transport:
                # - status/health updates
                # - effective config reporting
                # - remote config status
                # - package statuses
                # - connection settings requests and status
                # - custom messages
                response_msg = _build_response(agent_msg, pending_command)
        except ValueError as exc:
            response_msg = _build_error(str(exc))

        out_payload = response_msg.SerializeToString()
        await websocket.send(encode_message(out_payload))
        if response_msg.HasField("command"):
            STORE.mark_command_sent(client.client_id, pending_command)
            logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))


@app.get("/api/clients")
async def list_clients() -> Response:
    """List all tracked clients."""
    clients = [client.model_dump(mode="json") for client in STORE.list()]
    return jsonify({"clients": clients, "total": len(clients)})


@app.get("/api/clients/<client_id>")
async def get_client(client_id: str) -> Response:
    """Get a single client record."""
    record = STORE.get(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), 404
    return jsonify(record.model_dump(mode="json"))


@app.post("/api/clients/<client_id>/commands")
async def queue_command(client_id: str) -> Response:
    """Queue a command for a client."""
    payload = await request.get_json(silent=True)
    if not payload or "command" not in payload:
        return jsonify({"error": "command is required"}), 400
    command = str(payload["command"]).strip()
    if not command:
        return jsonify({"error": "command is required"}), 400
    cmd = STORE.queue_command(client_id, command)
    logger.info(LOG_REST_COMMAND, client_id, cmd.received_at)
    return jsonify(cmd.model_dump(mode="json")), 201


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
        return jsonify({"error": "payload is required"}), 400
    try:
        delayed = int(payload.get("delayed_comms_seconds", CONFIG.delayed_comms_seconds))
        significant = int(
            payload.get("significant_comms_seconds", CONFIG.significant_comms_seconds)
        )
    except (TypeError, ValueError):
        return jsonify({"error": "thresholds must be integers"}), 400
    if delayed <= 0 or significant <= 0:
        return jsonify({"error": "thresholds must be positive"}), 400
    if delayed >= significant:
        return jsonify({"error": "significant must be greater than delayed"}), 400
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
        return jsonify({"error": "payload is required"}), 400
    config_text = str(payload.get("config", "")).strip()
    if not config_text:
        return jsonify({"error": "config is required"}), 400
    version = payload.get("version")
    apply_at_raw = payload.get("apply_at")
    apply_at = None
    if apply_at_raw:
        try:
            apply_at = datetime.fromisoformat(str(apply_at_raw))
        except ValueError:
            return jsonify({"error": "apply_at must be ISO 8601"}), 400
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
    return Response(_HELP_HTML, content_type="text/html; charset=utf-8")


_WEB_UI_PATH = pathlib.Path(__file__).with_name("web_ui.html")
_WEB_UI_HTML = _WEB_UI_PATH.read_text(encoding=UTF8_ENCODING)

_HELP_PATH = pathlib.Path(__file__).with_name("help.html")
_HELP_HTML = _HELP_PATH.read_text(encoding=UTF8_ENCODING)
