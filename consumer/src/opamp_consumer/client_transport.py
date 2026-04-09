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
import ssl
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets

from opamp_consumer.proto import opamp_pb2
from opamp_consumer.transport import decode_message, encode_message
from shared.opamp_config import OPAMP_TRANSPORT_HEADER_NONE, UTF8_ENCODING

CONTENT_TYPE_PROTO = "application/x-protobuf"  # MIME type for protobuf HTTP payloads.
HEADER_CONTENT_TYPE = "Content-Type"  # HTTP header key used for request content type.
HEADER_AUTHORIZATION = "Authorization"  # HTTP/WebSocket header key for bearer authentication.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Error for unknown OpAMP framing header.
URL_SCHEME_HTTP = "http"  # URL scheme for plain HTTP transport.
URL_SCHEME_HTTPS = "https"  # URL scheme for TLS HTTP transport.
URL_SCHEME_WS = "ws"  # URL scheme for plain WebSocket transport.
URL_SCHEME_WSS = "wss"  # URL scheme for TLS WebSocket transport.


def _resolve_http_verify_setting(
    *,
    tls_verify: bool,
    tls_ca_file: str | None,
) -> bool | str:
    """Resolve httpx verify setting from consumer TLS options."""
    if not tls_verify:
        return False
    if tls_ca_file:
        return tls_ca_file
    return True


def _normalize_websocket_base_url(base_url: str) -> str:
    """Map HTTP(S) base URLs to WS(S) for websocket connections."""
    split_url = urlsplit(base_url)
    scheme = split_url.scheme.lower()
    if scheme == URL_SCHEME_HTTP:
        target_scheme = URL_SCHEME_WS
    elif scheme == URL_SCHEME_HTTPS:
        target_scheme = URL_SCHEME_WSS
    elif scheme in {URL_SCHEME_WS, URL_SCHEME_WSS}:
        target_scheme = scheme
    else:
        return base_url
    return urlunsplit(
        (
            target_scheme,
            split_url.netloc,
            split_url.path,
            split_url.query,
            split_url.fragment,
        )
    )


def _build_websocket_ssl_context(
    *,
    tls_verify: bool,
    tls_ca_file: str | None,
) -> ssl.SSLContext:
    """Build SSL context for WSS connections."""
    if not tls_verify:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
    if tls_ca_file:
        return ssl.create_default_context(cafile=tls_ca_file)
    return ssl.create_default_context()


async def send_http_message(
    *,
    msg: opamp_pb2.AgentToServer,
    base_url: str,
    opamp_http_path: str,
    handle_reply: Callable[[opamp_pb2.ServerToAgent], bool],
    authorization_header: str | None = None,
    tls_verify: bool = True,
    tls_ca_file: str | None = None,
) -> opamp_pb2.ServerToAgent:
    """Send AgentToServer via HTTP and parse ServerToAgent response."""
    url = f"{base_url}{opamp_http_path}"
    logging.getLogger(__name__).debug("Calling REST endpoint at %s", url)
    payload = msg.SerializeToString()
    headers: dict[str, str] = {HEADER_CONTENT_TYPE: CONTENT_TYPE_PROTO}
    if authorization_header:
        headers[HEADER_AUTHORIZATION] = authorization_header
    async with httpx.AsyncClient(
        verify=_resolve_http_verify_setting(
            tls_verify=tls_verify,
            tls_ca_file=tls_ca_file,
        )
    ) as client:
        response = await client.post(
            url,
            content=payload,
            headers=headers,
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
    authorization_header: str | None = None,
    tls_verify: bool = True,
    tls_ca_file: str | None = None,
) -> opamp_pb2.ServerToAgent:
    """Send AgentToServer via WebSocket and parse ServerToAgent response."""
    normalized_base_url = _normalize_websocket_base_url(base_url)
    url = f"{normalized_base_url}{opamp_http_path}"
    logging.getLogger(__name__).debug("Calling web socket at %s", url)

    async def _send_and_receive(**connect_kwargs):
        async with websockets.connect(url, **connect_kwargs) as web_socket:
            await web_socket.send(encode_message(msg.SerializeToString()))
            response_data = await web_socket.recv()
            await web_socket.close(code=1000)
            await web_socket.wait_closed()
            return response_data

    connect_kwargs: dict[str, object] = {}
    if authorization_header:
        connect_kwargs["additional_headers"] = {
            HEADER_AUTHORIZATION: authorization_header
        }
    if urlsplit(url).scheme.lower() == URL_SCHEME_WSS:
        connect_kwargs["ssl"] = _build_websocket_ssl_context(
            tls_verify=tls_verify,
            tls_ca_file=tls_ca_file,
        )

    data = await _send_and_receive(**connect_kwargs)

    if isinstance(data, str):
        data = data.encode(UTF8_ENCODING)
    header, payload = decode_message(data)
    if header != OPAMP_TRANSPORT_HEADER_NONE:
        raise ValueError(ERR_UNSUPPORTED_HEADER)
    reply = opamp_pb2.ServerToAgent()
    reply.ParseFromString(payload)

    handle_reply(reply)
    return reply
