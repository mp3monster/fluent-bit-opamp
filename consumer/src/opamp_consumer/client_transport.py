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

"""Transport send helpers for OpAMP client HTTP and WebSocket communication."""

from __future__ import annotations

import logging
from typing import Callable

import httpx
import websockets

from opamp_consumer.proto import opamp_pb2
from opamp_consumer.transport import decode_message, encode_message
from shared.opamp_config import OPAMP_TRANSPORT_HEADER_NONE, UTF8_ENCODING

CONTENT_TYPE_PROTO = "application/x-protobuf"
HEADER_CONTENT_TYPE = "Content-Type"
ERR_UNSUPPORTED_HEADER = "unsupported transport header"


async def send_http_message(
    *,
    msg: opamp_pb2.AgentToServer,
    base_url: str,
    opamp_http_path: str,
    handle_reply: Callable[[opamp_pb2.ServerToAgent], bool],
) -> opamp_pb2.ServerToAgent:
    """Send AgentToServer via HTTP and parse ServerToAgent response."""
    url = f"{base_url}{opamp_http_path}"
    logging.getLogger(__name__).debug("Calling REST endpoint at %s", url)
    payload = msg.SerializeToString()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            content=payload,
            headers={HEADER_CONTENT_TYPE: CONTENT_TYPE_PROTO},
        )
        response.raise_for_status()
        reply = opamp_pb2.ServerToAgent()
        reply.ParseFromString(response.content)
        handle_reply(reply)
        return reply


async def send_websocket_message(
    *,
    msg: opamp_pb2.AgentToServer,
    base_url: str,
    opamp_http_path: str,
    handle_reply: Callable[[opamp_pb2.ServerToAgent], bool],
) -> opamp_pb2.ServerToAgent:
    """Send AgentToServer via WebSocket and parse ServerToAgent response."""
    url = f"{base_url}{opamp_http_path}"
    logging.getLogger(__name__).debug("Calling web socket at %s", url)

    async with websockets.connect(url) as web_socket:
        await web_socket.send(encode_message(msg.SerializeToString()))
        data = await web_socket.recv()
        await web_socket.close(code=1000)
        await web_socket.wait_closed()
    if isinstance(data, str):
        data = data.encode(UTF8_ENCODING)
    header, payload = decode_message(data)
    if header != OPAMP_TRANSPORT_HEADER_NONE:
        raise ValueError(ERR_UNSUPPORTED_HEADER)
    reply = opamp_pb2.ServerToAgent()
    reply.ParseFromString(payload)

    handle_reply(reply)
    return reply
