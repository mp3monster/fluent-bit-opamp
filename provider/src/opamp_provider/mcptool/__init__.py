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

"""MCP tool endpoints package."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from quart import Quart

from opamp_provider.mcptool.routes import mcpserver, mcptool_blueprint

logger = logging.getLogger(__name__)


def register_tool_routes(app: Quart) -> None:
    """Register /tool routes on the provided Quart app."""
    app.register_blueprint(mcptool_blueprint)


def register_mcp_transport(app: Quart, sse_path: str = "/sse") -> bool:
    """Expose FastMCP SSE transport through the Quart ASGI app when available."""
    http_app_factory = getattr(mcpserver, "http_app", None)
    if not callable(http_app_factory):
        logger.info("FastMCP http transport is unavailable; skipping Quart MCP exposure")
        return False

    try:
        mcp_asgi_app = http_app_factory(path=sse_path, transport="sse")
    except Exception:
        logger.exception("Failed to initialise FastMCP HTTP app; skipping MCP exposure")
        return False

    quart_asgi_app = app.asgi_app
    normalized_sse = sse_path.rstrip("/") or "/"
    mcp_prefixes = (normalized_sse, "/messages")

    async def _dispatch(  # type: ignore[override]
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        path = str(scope.get("path", ""))
        scope_type = str(scope.get("type", ""))
        if scope_type in {"http", "websocket"} and any(
            path == prefix or path.startswith(f"{prefix}/") for prefix in mcp_prefixes
        ):
            await mcp_asgi_app(scope, receive, send)
            return
        await quart_asgi_app(scope, receive, send)

    app.asgi_app = _dispatch
    logger.info(
        "FastMCP transport exposed through Quart at %s (messages endpoint: /messages)",
        normalized_sse,
    )
    return True


__all__ = [
    "register_tool_routes",
    "register_mcp_transport",
    "mcptool_blueprint",
    "mcpserver",
]
