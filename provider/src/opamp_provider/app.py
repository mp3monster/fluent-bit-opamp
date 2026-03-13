"""Quart OpAMP server skeleton."""

from __future__ import annotations

import logging

from google.protobuf import text_format
from quart import Quart, Response, request, websocket

from opamp_provider.config import CONFIG
from opamp_provider.proto import opamp_pb2
from opamp_provider.transport import decode_message, encode_message
from shared.opamp_config import OPAMP_HTTP_PATH, OPAMP_TRANSPORT_HEADER_NONE, UTF8_ENCODING

app = Quart(__name__)
logger = logging.getLogger(__name__)

CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
LOG_HTTP_MSG = "opamp http AgentToServer:\n%s"  # Log format for HTTP messages.
LOG_WS_MSG = "opamp ws AgentToServer:\n%s"  # Log format for WebSocket messages.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.


def _build_response(request_msg: opamp_pb2.AgentToServer) -> opamp_pb2.ServerToAgent:
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

    # TODO(opamp): Implement per-operation processing for HTTP transport:
    # - status/health updates
    # - effective config reporting
    # - remote config status
    # - package statuses
    # - connection settings requests and status
    # - custom messages
    response_msg = _build_response(agent_msg)
    payload = response_msg.SerializeToString()
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
                # TODO(opamp): Implement per-operation processing for WebSocket transport:
                # - status/health updates
                # - effective config reporting
                # - remote config status
                # - package statuses
                # - connection settings requests and status
                # - custom messages
                response_msg = _build_response(agent_msg)
        except ValueError as exc:
            response_msg = _build_error(str(exc))

        out_payload = response_msg.SerializeToString()
        await websocket.send(encode_message(out_payload))
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.
