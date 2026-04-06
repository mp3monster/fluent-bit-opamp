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

import opamp_consumer.client_transport as client_transport
from opamp_consumer.proto import opamp_pb2
from opamp_consumer.transport import encode_message


def _server_reply_payload(instance_uid: bytes) -> bytes:
    reply = opamp_pb2.ServerToAgent()
    reply.instance_uid = instance_uid
    return reply.SerializeToString()


def test_send_http_message_adds_authorization_header(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
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
