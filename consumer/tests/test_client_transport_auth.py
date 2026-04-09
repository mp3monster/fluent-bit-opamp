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

import asyncio
import ssl
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import opamp_consumer.client_transport as client_transport
from opamp_consumer.proto import opamp_pb2
from opamp_consumer.transport import encode_message

REPO_ROOT = Path(__file__).resolve().parents[2]
TLS_CERT_SCRIPT = REPO_ROOT / "scripts" / "generate_self_signed_tls_cert.py"


def _server_reply_payload(instance_uid: bytes) -> bytes:
    reply = opamp_pb2.ServerToAgent()
    reply.instance_uid = instance_uid
    return reply.SerializeToString()


class _HttpsOpAMPHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        request_payload = self.rfile.read(content_length)
        request = opamp_pb2.AgentToServer()
        request.ParseFromString(request_payload)

        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = request.instance_uid
        response_payload = reply.SerializeToString()

        self.send_response(200)
        self.send_header("Content-Type", client_transport.CONTENT_TYPE_PROTO)
        self.send_header("Content-Length", str(len(response_payload)))
        self.end_headers()
        self.wfile.write(response_payload)

    def log_message(self, _format: str, *args) -> None:
        return None


def _generate_self_signed_cert(cert_file: Path, key_file: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(TLS_CERT_SCRIPT),
            "--skip-dependency-install",
            "--force",
            "--common-name",
            "localhost",
            "--dns-name",
            "localhost",
            "--ip-address",
            "127.0.0.1",
            "--cert-file",
            str(cert_file),
            "--key-file",
            str(key_file),
            "--days",
            "365",
        ],
        check=True,
    )


def _start_https_server(cert_file: Path, key_file: Path) -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), _HttpsOpAMPHandler)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(
        certfile=str(cert_file),
        keyfile=str(key_file),
    )
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server, server_thread


def test_send_http_message_adds_authorization_header(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content, headers):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResponse(_server_reply_payload(instance_uid=b"abc"))

    monkeypatch.setattr(client_transport.httpx, "AsyncClient", FakeAsyncClient)

    msg = opamp_pb2.AgentToServer()
    msg.instance_uid = b"abc"
    handled = {"count": 0}

    def _handle_reply(_reply: opamp_pb2.ServerToAgent) -> bool:
        handled["count"] += 1
        return True

    reply = asyncio.run(
        client_transport.send_http_message(
            msg=msg,
            base_url="http://localhost:4320",
            opamp_http_path="/v1/opamp",
            handle_reply=_handle_reply,
            authorization_header="Bearer test-token",
        )
    )

    assert reply.instance_uid == b"abc"
    assert handled["count"] == 1
    assert captured["headers"][client_transport.HEADER_CONTENT_TYPE] == (
        client_transport.CONTENT_TYPE_PROTO
    )
    assert captured["headers"][client_transport.HEADER_AUTHORIZATION] == (
        "Bearer test-token"
    )
    assert captured["client_kwargs"]["verify"] is True


def test_send_websocket_message_adds_additional_headers(monkeypatch) -> None:
    captured = {}

    class FakeWebSocket:
        async def send(self, data: bytes) -> None:
            captured["sent"] = data

        async def recv(self) -> bytes:
            return encode_message(_server_reply_payload(instance_uid=b"uid-1"))

        async def close(self, code=1000) -> None:
            captured["close_code"] = code

        async def wait_closed(self) -> None:
            captured["wait_closed"] = True

    class FakeConnect:
        async def __aenter__(self):
            return FakeWebSocket()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _fake_connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeConnect()

    monkeypatch.setattr(client_transport.websockets, "connect", _fake_connect)

    msg = opamp_pb2.AgentToServer()
    msg.instance_uid = b"uid-1"

    reply = asyncio.run(
        client_transport.send_websocket_message(
            msg=msg,
            base_url="ws://localhost:4320",
            opamp_http_path="/v1/opamp",
            handle_reply=lambda _reply: True,
            authorization_header="Bearer ws-token",
        )
    )

    assert reply.instance_uid == b"uid-1"
    assert captured["kwargs"]["additional_headers"] == {
        client_transport.HEADER_AUTHORIZATION: "Bearer ws-token"
    }


def test_send_websocket_message_normalizes_https_to_wss_and_sets_ssl_context(
    monkeypatch,
) -> None:
    captured = {}

    class FakeWebSocket:
        async def send(self, data: bytes) -> None:
            captured["sent"] = data

        async def recv(self) -> bytes:
            return encode_message(_server_reply_payload(instance_uid=b"uid-2"))

        async def close(self, code=1000) -> None:
            captured["close_code"] = code

        async def wait_closed(self) -> None:
            captured["wait_closed"] = True

    class FakeConnect:
        async def __aenter__(self):
            return FakeWebSocket()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _fake_connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeConnect()

    monkeypatch.setattr(client_transport.websockets, "connect", _fake_connect)

    msg = opamp_pb2.AgentToServer()
    msg.instance_uid = b"uid-2"

    reply = asyncio.run(
        client_transport.send_websocket_message(
            msg=msg,
            base_url="https://localhost:4320",
            opamp_http_path="/v1/opamp",
            handle_reply=lambda _reply: True,
        )
    )

    assert reply.instance_uid == b"uid-2"
    assert captured["url"].startswith("wss://")
    assert "ssl" in captured["kwargs"]


def test_send_http_message_uses_tls_verify_false_when_requested(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content, headers):
            return FakeResponse(_server_reply_payload(instance_uid=b"abc"))

    monkeypatch.setattr(client_transport.httpx, "AsyncClient", FakeAsyncClient)

    msg = opamp_pb2.AgentToServer()
    msg.instance_uid = b"abc"

    asyncio.run(
        client_transport.send_http_message(
            msg=msg,
            base_url="https://localhost:4320",
            opamp_http_path="/v1/opamp",
            handle_reply=lambda _reply: True,
            tls_verify=False,
        )
    )

    assert captured["client_kwargs"]["verify"] is False


def test_send_http_message_performs_real_https_handshake_with_tls_verify_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_file = Path(tmpdir) / "test-cert.pem"
        key_file = Path(tmpdir) / "test-key.pem"
        _generate_self_signed_cert(cert_file, key_file)

        server, server_thread = _start_https_server(cert_file, key_file)
        try:
            server_host, server_port = server.server_address
            msg = opamp_pb2.AgentToServer()
            msg.instance_uid = b"https-real-handshake"

            reply = asyncio.run(
                client_transport.send_http_message(
                    msg=msg,
                    base_url=f"https://{server_host}:{server_port}",
                    opamp_http_path="/v1/opamp",
                    handle_reply=lambda _reply: True,
                    tls_verify=False,
                )
            )
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

    assert reply.instance_uid == b"https-real-handshake"
