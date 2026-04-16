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

"""Deterministic rule-first planner implementation."""

from __future__ import annotations

import re
from typing import Any

from opamp_broker.planner.constants import (
    REQUIRES_CONFIRMATION_KEY,
    RESPONSE_TEXT_KEY,
    TOOL_ARGS_KEY,
    TOOL_NAME_KEY,
)


class RuleFirstPlanner:
    """Deterministic fallback planner when LLM planning is unavailable."""

    async def plan(self, *, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Create a tool-constrained plan using deterministic keyword rules."""
        tool_names = [str(tool.get("name", "")).strip() for tool in tools]
        normalized = text.strip().lower()
        parts = text.split()
        target = parts[-1] if len(parts) > 1 else None

        direct_tool = _find_direct_tool_request(text=text, tool_names=tool_names)
        if direct_tool is not None:
            direct_target = _extract_direct_target(text=text, tool_name=direct_tool)
            requires_confirmation = any(
                keyword in direct_tool.lower()
                for keyword in ("restart", "delete", "remove", "shutdown")
            )
            return {
                RESPONSE_TEXT_KEY: "",
                TOOL_NAME_KEY: direct_tool,
                TOOL_ARGS_KEY: (
                    {"target": direct_target}
                    if direct_target
                    else {}
                ),
                REQUIRES_CONFIRMATION_KEY: requires_confirmation,
            }

        if any(
            phrase in normalized
            for phrase in (
                "tools",
                "available tools",
                "what can you do",
                "capabilities",
                "commands",
            )
        ):
            return {
                RESPONSE_TEXT_KEY: _format_tool_catalog(tools),
                TOOL_NAME_KEY: None,
                TOOL_ARGS_KEY: {},
                REQUIRES_CONFIRMATION_KEY: False,
            }

        if "help" in normalized or not normalized:
            return {
                RESPONSE_TEXT_KEY: (
                    "Try `/opamp status collector-a`, `/opamp health collector-a`, "
                    "`/opamp config collector-a`, or ask me what is wrong with an agent."
                ),
                TOOL_NAME_KEY: None,
                TOOL_ARGS_KEY: {},
                REQUIRES_CONFIRMATION_KEY: False,
            }

        for prefix, tool_hint in [
            ("status", "status"),
            ("health", "health"),
            ("config", "config"),
            ("diff", "diff"),
            ("restart", "restart"),
        ]:
            if normalized.startswith(prefix):
                chosen = next((name for name in tool_names if tool_hint in name.lower()), None)
                return {
                    RESPONSE_TEXT_KEY: "",
                    TOOL_NAME_KEY: chosen,
                    TOOL_ARGS_KEY: {"target": target} if (chosen and target) else {},
                    REQUIRES_CONFIRMATION_KEY: prefix in {"restart"},
                }

        chosen = next((name for name in tool_names if "health" in name.lower()), None) or next(
            (name for name in tool_names if "status" in name.lower()), None
        )
        return {
            RESPONSE_TEXT_KEY: "",
            TOOL_NAME_KEY: chosen,
            TOOL_ARGS_KEY: {"target": target} if (chosen and target) else {},
            REQUIRES_CONFIRMATION_KEY: False,
        }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    """Render a human-readable summary of discovered tools."""
    usable_tools = [tool for tool in tools if str(tool.get("name", "")).strip()]
    if not usable_tools:
        return (
            "I can use MCP tools to help, but I haven't discovered any yet. "
            "Please check that the OpAMP provider is online."
        )

    lines = ["Available MCP tools:"]
    for tool in sorted(usable_tools, key=lambda item: str(item.get("name", ""))):
        lines.append(_format_tool_line(tool))
    lines.append(
        "Tell me what you want to do and the target, for example: "
        "`status collector-a` or `health collector-a`."
    )
    return "\n".join(lines)


def _format_tool_line(tool: dict[str, Any]) -> str:
    """Render one tool with purpose and argument hints."""
    name = str(tool.get("name", "")).strip()
    description = str(tool.get("description", "")).strip() or "No description provided."
    args_hint = _format_args_hint(tool.get("inputSchema", {}))
    if args_hint:
        return f"- `{name}`: {description}. Args: {args_hint}"
    return f"- `{name}`: {description}. Args: none."


def _format_args_hint(input_schema: Any) -> str:
    """Build concise argument guidance from a JSON Schema-like object."""
    if not isinstance(input_schema, dict):
        return ""
    properties = input_schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return ""

    required_values = input_schema.get("required", [])
    required = {
        str(value).strip()
        for value in required_values
        if isinstance(value, str) and value.strip()
    }
    rendered: list[str] = []
    for name, schema in properties.items():
        field_name = str(name).strip()
        if not field_name:
            continue
        field_type = ""
        if isinstance(schema, dict):
            raw_type = schema.get("type")
            if isinstance(raw_type, str) and raw_type.strip():
                field_type = raw_type.strip()
        suffix = "required" if field_name in required else "optional"
        if field_type:
            rendered.append(f"{field_name} ({field_type}, {suffix})")
        else:
            rendered.append(f"{field_name} ({suffix})")
    return ", ".join(rendered)


def _find_direct_tool_request(text: str, tool_names: list[str]) -> str | None:
    """Return explicitly requested tool name when user types a tool identifier."""
    normalized = text.strip().lower()
    if not normalized:
        return None

    for name in tool_names:
        stripped_name = name.strip()
        if not stripped_name:
            continue
        lowered_name = stripped_name.lower()
        if normalized == lowered_name:
            return stripped_name
        if normalized.startswith(f"{lowered_name} "):
            return stripped_name
        if re.search(rf"\b{re.escape(lowered_name)}\b", normalized):
            return stripped_name
    return None


def _extract_direct_target(text: str, tool_name: str) -> str | None:
    """Extract a simple trailing target token from direct tool invocation text."""
    pattern = re.compile(rf"^\s*{re.escape(tool_name)}\s+(?P<target>\S+)")
    match = pattern.search(text)
    if not match:
        return None
    target = match.group("target").strip()
    return target if target else None
