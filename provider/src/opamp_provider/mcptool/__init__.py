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

import asyncio
import json
import logging
from contextlib import suppress
from http import HTTPStatus
from typing import Any, Awaitable, Callable, Literal

from quart import Quart

from opamp_provider import auth as provider_auth
from opamp_provider import config as provider_config
from opamp_provider.mcptool.routes import mcpserver, mcptool_blueprint

logger = logging.getLogger(__name__)
ERR_UI_AUTH_CONFIG_INVALID = "invalid ui-use-authorization configuration"


def register_tool_routes(app: Quart) -> None:
    """Register /tool routes on the provided Quart app."""
    app.register_blueprint(mcptool_blueprint)


def _normalize_path(path: str) -> str:
    """Normalize path for robust prefix matching."""
    return path.rstrip("/") or "/"


def _path_matches_prefix(path: str, prefix: str) -> bool:
    """Return whether request path targets a prefix or one of its descendants."""
    return path == prefix or path.startswith(f"{prefix}/")


def _provider_authorization_mode_to_auth_mode(provider_mode: str) -> str | None:
    """Map provider config authorization values to auth module mode."""
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_NONE:
        return provider_auth.AUTH_MODE_DISABLED
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN:
        return provider_auth.AUTH_MODE_STATIC
    if provider_mode == provider_config.OPAMP_USE_AUTHORIZATION_IDP:
        return provider_auth.AUTH_MODE_JWT
    return None


def _evaluate_ui_scope_auth(scope: dict[str, Any]) -> provider_auth.AuthDecision:
    """Authorize non-OpAMP ASGI scopes using provider.ui-use-authorization."""
    ui_mode = str(provider_config.CONFIG.ui_use_authorization).strip().lower()
    mapped_mode = _provider_authorization_mode_to_auth_mode(ui_mode)
    if mapped_mode is None:
        logger.error(
            "unsupported provider.%s value=%s",
            provider_config.CFG_UI_USE_AUTHORIZATION,
            ui_mode,
        )
        return provider_auth.AuthDecision(
            allowed=False,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            error=ERR_UI_AUTH_CONFIG_INVALID,
            reason=f"unsupported mode {ui_mode}",
        )
    return provider_auth.evaluate_required_asgi_scope_auth(
        scope,
        mode=mapped_mode,
        static_token=provider_auth.UI_AUTH_SETTINGS.static_token,
        jwt_settings=provider_auth.UI_AUTH_SETTINGS,
    )


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

    class _ASGILifespanController:
        """Manage ASGI lifespan startup/shutdown for mounted FastMCP apps."""

        def __init__(self, asgi_app: Any, label: str) -> None:
            self._asgi_app = asgi_app
            self._label = label
            self._task: asyncio.Task[None] | None = None
            self._receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            self._startup_event = asyncio.Event()
            self._shutdown_event = asyncio.Event()
            self._startup_error: str | None = None

        async def _run(self) -> None:
            async def receive() -> dict[str, Any]:
                return await self._receive_queue.get()

            async def send(message: dict[str, Any]) -> None:
                msg_type = str(message.get("type", ""))
                if msg_type == "lifespan.startup.complete":
                    self._startup_event.set()
                    return
                if msg_type == "lifespan.startup.failed":
                    self._startup_error = str(message.get("message", "unknown startup failure"))
                    self._startup_event.set()
                    return
                if msg_type in {"lifespan.shutdown.complete", "lifespan.shutdown.failed"}:
                    self._shutdown_event.set()

            scope = {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.3"}}
            await self._asgi_app(scope, receive, send)

        async def startup(self) -> None:
            if self._task is None:
                self._task = asyncio.create_task(self._run(), name=f"fastmcp-lifespan-{self._label}")
                await self._receive_queue.put({"type": "lifespan.startup"})
            await self._startup_event.wait()
            if self._startup_error:
                raise RuntimeError(
                    f"FastMCP lifespan startup failed for {self._label}: {self._startup_error}"
                )

        async def shutdown(self) -> None:
            if self._task is None:
                return
            await self._receive_queue.put({"type": "lifespan.shutdown"})
            await self._shutdown_event.wait()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    lifespan_controllers = [
        _ASGILifespanController(mcp_asgi_app, mode)
        for mode, mcp_asgi_app in app_mappings
    ]

    @app.before_serving
    async def _start_fastmcp_lifespans() -> None:
        for controller in lifespan_controllers:
            await controller.startup()

    @app.after_serving
    async def _stop_fastmcp_lifespans() -> None:
        for controller in lifespan_controllers:
            with suppress(Exception):
                await controller.shutdown()

    quart_asgi_app = app.asgi_app
    sse_prefixes = (normalized_sse, "/messages")

    async def _send_auth_rejection(
        send: Callable[[dict[str, Any]], Awaitable[None]],
        decision: provider_auth.AuthDecision,
    ) -> None:
        payload = json.dumps({"error": decision.error or "unauthorized"}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("utf-8")),
        ]
        if decision.status_code == HTTPStatus.UNAUTHORIZED:
            headers.append(
                (
                    b"www-authenticate",
                    provider_auth.WWW_AUTHENTICATE_BEARER.encode("utf-8"),
                )
            )
        await send(
            {
                "type": "http.response.start",
                "status": int(decision.status_code),
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
                "more_body": False,
            }
        )

    async def _send_websocket_auth_rejection(
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        await send({"type": "websocket.close", "code": 1008})

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
                    decision = _evaluate_ui_scope_auth(scope)
                    if not decision.allowed:
                        if scope_type == "websocket":
                            await _send_websocket_auth_rejection(send)
                        else:
                            await _send_auth_rejection(send, decision)
                        return
                    await mcp_asgi_app(scope, receive, send)
                    return
                if mode == "streamable-http" and _path_matches_prefix(path, normalized_streamable):
                    decision = _evaluate_ui_scope_auth(scope)
                    if not decision.allowed:
                        if scope_type == "websocket":
                            await _send_websocket_auth_rejection(send)
                        else:
                            await _send_auth_rejection(send, decision)
                        return
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
