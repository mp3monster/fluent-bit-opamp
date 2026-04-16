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

"""In-memory MCP tool registry used by planning and execution nodes.

The registry caches tool metadata so graph nodes can make quick routing
decisions without issuing a network request on every user message.
"""

from __future__ import annotations

from typing import Any

from opamp_broker.mcp.client import MCPClient


class MCPToolRegistry:
    """Cache and lookup wrapper around ``MCPClient`` tool discovery."""

    def __init__(self, client: MCPClient) -> None:
        """Create a registry bound to one MCP transport client.

        Args:
            client: MCP client used for initialization and tool listing calls.

        Returns:
            None: Initializes an empty in-memory tool cache.
        """
        self.client = client
        self._tools: dict[str, dict[str, Any]] = {}

    async def refresh(self) -> dict[str, dict[str, Any]]:
        """Refresh the local cache from provider MCP metadata.

        Why this approach:
        discovery is run once and cached to reduce latency during conversation
        flow while still allowing explicit refreshes when needed.

        Returns:
            dict[str, dict[str, Any]]: Mapping of tool name to tool metadata.
        """
        tools = await self.client.discover_tools()
        self._tools = {tool["name"]: tool for tool in tools if "name" in tool}
        return self._tools

    def get(self, name: str) -> dict[str, Any] | None:
        """Return cached metadata for one tool name if present.

        Args:
            name: Tool identifier to retrieve.

        Returns:
            dict[str, Any] | None: Tool metadata or ``None`` when unknown.
        """
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """List known tool names sorted for deterministic display/routing.

        Returns:
            list[str]: Sorted list of cached tool names.
        """
        return sorted(self._tools.keys())

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one discovered tool against the provider MCP endpoint."""
        return await self.client.call_tool(name, arguments)
