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

"""MCP tool endpoints package.

References:
- Model Context Protocol (MCP) specification:
  https://modelcontextprotocol.io/specification
- FastMCP documentation:
  https://gofastmcp.com/
- ASGI specification:
  https://asgi.readthedocs.io/en/latest/specs/main.html
- Quart documentation:
  https://quart.palletsprojects.com/

This module bridges FastMCP's ASGI transport app(s) into Quart so MCP tools can
be exposed over SSE and/or Streamable HTTP.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Literal

from quart import Quart

from opamp_provider.mcptool.routes import mcpserver, mcptool_blueprint

logger = logging.getLogger(__name__)


def register_tool_routes(app: Quart) -> None:
    """Register /tool routes on the provided Quart app."""
    app.register_blueprint(mcptool_blueprint)


def _normalize_path(path: str) -> str:
    """Normalize path for robust prefix matching."""
    return path.rstrip("/") or "/"


def _path_matches_prefix(path: str, prefix: str) -> bool:
    """Return whether request path targets a prefix or one of its descendants."""
    return path == prefix or path.startswith(f"{prefix}/")


def register_mcp_transport(
    app: Quart,
    sse_path: str = "/sse",
    streamable_http_path: str = "/mcp",
    transport: Literal["sse", "streamable-http", "both"] = "sse",
) -> bool:
    """Expose FastMCP transports through the Quart ASGI app when available."""
    http_app_factory = getattr(mcpserver, "http_app", None)
    if not callable(http_app_factory):
        logger.info("FastMCP http transport is unavailable; skipping Quart MCP exposure")
        return False

    transport_mode = transport.strip().lower()
    if transport_mode not in {"sse", "streamable-http", "both"}:
        logger.error("Invalid MCP transport mode '%s'; expected sse, streamable-http, or both", transport)
        return False

    normalized_sse = _normalize_path(sse_path)
    normalized_streamable = _normalize_path(streamable_http_path)

    app_mappings: list[tuple[str, Any]] = []
    if transport_mode in {"sse", "both"}:
        try:
            app_mappings.append(("sse", http_app_factory(path=normalized_sse, transport="sse")))
        except Exception:
            logger.exception("Failed to initialise FastMCP SSE app")
            if transport_mode == "sse":
                return False

    if transport_mode in {"streamable-http", "both"}:
        try:
            app_mappings.append(
                (
                    "streamable-http",
                    http_app_factory(
                        path=normalized_streamable,
                        transport="streamable-http",
                    ),
                )
            )
        except Exception:
            logger.exception("Failed to initialise FastMCP Streamable HTTP app")
            if transport_mode == "streamable-http":
                return False

    if not app_mappings:
        logger.info("No MCP transport app was initialised; skipping Quart MCP exposure")
        return False

    quart_asgi_app = app.asgi_app
    sse_prefixes = (normalized_sse, "/messages")

    async def _dispatch(  # type: ignore[override]
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        path = str(scope.get("path", ""))
        scope_type = str(scope.get("type", ""))

        if scope_type in {"http", "websocket"}:
            for mode, mcp_asgi_app in app_mappings:
                if mode == "sse" and any(
                    _path_matches_prefix(path, prefix) for prefix in sse_prefixes
                ):
                    await mcp_asgi_app(scope, receive, send)
                    return
                if mode == "streamable-http" and _path_matches_prefix(path, normalized_streamable):
                    await mcp_asgi_app(scope, receive, send)
                    return

        await quart_asgi_app(scope, receive, send)

    app.asgi_app = _dispatch
    if transport_mode == "sse":
        logger.info(
            "FastMCP SSE transport exposed through Quart at %s (messages endpoint: /messages)",
            normalized_sse,
        )
    elif transport_mode == "streamable-http":
        logger.info(
            "FastMCP Streamable HTTP transport exposed through Quart at %s",
            normalized_streamable,
        )
    else:
        logger.info(
            "FastMCP SSE transport exposed at %s (messages endpoint: /messages) and Streamable HTTP at %s",
            normalized_sse,
            normalized_streamable,
        )
    return True


__all__ = [
    "register_tool_routes",
    "register_mcp_transport",
    "mcptool_blueprint",
    "mcpserver",
]
