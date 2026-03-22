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

from __future__ import annotations

from quart import Quart
import pytest

from opamp_provider import mcptool


@pytest.mark.asyncio
async def test_register_mcp_transport_wraps_quart_asgi_dispatch() -> None:
    app = Quart(__name__)
    calls: list[str] = []

    async def fake_mcp_app(scope, _receive, _send):  # noqa: ANN001
        calls.append(str(scope.get("path", "")))

    class FakeMcpServer:
        def http_app(self, *, path: str, transport: str):  # noqa: ANN201
            assert path == "/sse"
            assert transport == "sse"
            return fake_mcp_app

    original_asgi_app = app.asgi_app
    original_server = mcptool.mcpserver
    try:
        mcptool.mcpserver = FakeMcpServer()  # type: ignore[assignment]
        enabled = mcptool.register_mcp_transport(app, sse_path="/sse")
        assert enabled is True
        assert app.asgi_app is not original_asgi_app

        async def _noop_receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _noop_send(_message: dict) -> None:
            return None

        await app.asgi_app({"type": "http", "path": "/sse"}, _noop_receive, _noop_send)
        await app.asgi_app(
            {"type": "http", "path": "/messages"},
            _noop_receive,
            _noop_send,
        )
    finally:
        mcptool.mcpserver = original_server  # type: ignore[assignment]

    assert calls == ["/sse", "/messages"]


def test_register_mcp_transport_skips_when_http_app_unavailable() -> None:
    app = Quart(__name__)
    original_asgi_func = app.asgi_app.__func__
    original_server = mcptool.mcpserver
    try:
        mcptool.mcpserver = object()  # type: ignore[assignment]
        enabled = mcptool.register_mcp_transport(app, sse_path="/sse")
    finally:
        mcptool.mcpserver = original_server  # type: ignore[assignment]

    assert enabled is False
    assert app.asgi_app.__func__ is original_asgi_func
