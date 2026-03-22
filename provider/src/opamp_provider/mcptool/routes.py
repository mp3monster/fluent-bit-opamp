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

"""Blueprint routes for /tool endpoints."""

from __future__ import annotations

from typing import Any

from quart import Blueprint, Response, jsonify

from opamp_provider.commands import get_command_metadata
from opamp_provider.state import STORE

try:
    from fastmcp import FastMCP
except ModuleNotFoundError:  # pragma: no cover - dependency may be optional in tests
    class FastMCP:  # type: ignore[override]
        """Fallback shim when fastmcp is unavailable."""

        def __init__(self, _name: str) -> None:
            pass

        def tool(self, *args: Any, **kwargs: Any):  # noqa: ANN002, ANN003
            def _decorator(func):  # noqa: ANN001
                return func

            return _decorator

mcptool_blueprint = Blueprint("mcptool", __name__)
mcpserver = FastMCP("OpAMP Server")


def _list_connected_otel_agents_payload() -> dict[str, Any]:
    """Build the connected otel agents payload shared by HTTP and MCP tools."""
    agents = [
        client.model_dump(mode="json")
        for client in STORE.list()
        if not client.disconnected
    ]
    return {"agents": agents, "total": len(agents)}


def _list_all_commands_payload() -> dict[str, Any]:
    """Build the commands payload shared by HTTP and MCP tools."""
    standard_commands = get_command_metadata(
        parameter_exclude_opamp_standard=False,
        custom_only=False,
    )
    custom_commands = get_command_metadata(
        parameter_exclude_opamp_standard=True,
        custom_only=False,
    )
    merged: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for command in [*standard_commands, *custom_commands]:
        key = (
            str(command.get("classifier", "")).strip().lower(),
            str(command.get("operation", "")).strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(command)
    merged.sort(key=lambda item: str(item.get("displayname", "")).lower())
    return {"commands": merged, "total": len(merged)}


def _tool_openapi_spec_payload() -> dict[str, Any]:
    """Build the OpenAPI specification payload shared by HTTP and MCP tools."""
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "OpAMP Provider Tool API",
            "version": "1.0.0",
            "description": "OpenAPI specification for /tool endpoints.",
        },
        "paths": {
            "/tool/otelAgents": {
                "get": {
                    "summary": "List connected agents",
                    "description": "Returns agents that are not disconnected.",
                    "responses": {
                        "200": {
                            "description": "Connected agents returned successfully.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "agents": {
                                                "type": "array",
                                                "items": {"type": "object"},
                                            },
                                            "total": {"type": "integer"},
                                        },
                                        "required": ["agents", "total"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/tool/commands": {
                "get": {
                    "summary": "List available commands",
                    "description": (
                        "Returns all available commands, including OpAMP-standard and custom."
                    ),
                    "responses": {
                        "200": {
                            "description": "Commands returned successfully.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "commands": {
                                                "type": "array",
                                                "items": {"type": "object"},
                                            },
                                            "total": {"type": "integer"},
                                        },
                                        "required": ["commands", "total"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/tool": {
                "get": {
                    "summary": "Get tool API specification",
                    "description": "Returns this OpenAPI specification document.",
                    "responses": {
                        "200": {
                            "description": "Tool OpenAPI specification returned successfully."
                        }
                    },
                }
            },
        },
    }
    return spec


@mcptool_blueprint.get("/tool/otelAgents")
async def list_connected_otel_agents() -> Response:
    """List only agents that are currently not marked disconnected."""
    return jsonify(_list_connected_otel_agents_payload())


@mcptool_blueprint.get("/tool")
async def tool_openapi_spec() -> Response:
    """Return an OpenAPI specification for /tool endpoints."""
    return jsonify(_tool_openapi_spec_payload())


@mcptool_blueprint.get("/tool/commands")
async def list_all_commands() -> Response:
    """Return all known commands, including OpAMP-standard and custom."""
    return jsonify(_list_all_commands_payload())


@mcpserver.tool(
    name="tool_openapi_spec",
    description="Return the OpenAPI specification for OpAMP /tool endpoints.",
)
def mcp_tool_openapi_spec() -> dict[str, Any]:
    """Expose /tool OpenAPI specification through MCP."""
    return _tool_openapi_spec_payload()


@mcpserver.tool(
    name="tool_otel_agents",
    description="Return OpAMP agents that are not disconnected.",
)
def mcp_tool_otel_agents() -> dict[str, Any]:
    """Expose connected otel agents through MCP."""
    return _list_connected_otel_agents_payload()


@mcpserver.tool(
    name="tool_commands",
    description="Return all available OpAMP commands, both custom and standard.",
)
def mcp_tool_commands() -> dict[str, Any]:
    """Expose full command catalog through MCP."""
    return _list_all_commands_payload()
