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

BOOLEAN_TRUE_VALUES = {"1", "true", "yes", "on"}
BOOLEAN_FALSE_VALUES = {"0", "false", "no", "off"}
ARGUMENT_KEY_VALUE_PATTERN = re.compile(
    r"(?P<key>(?:--)?[A-Za-z_][A-Za-z0-9_.-]*)\s*(?:=|:)\s*"
    r"(?P<value>\"[^\"]*\"|'[^']*'|\S+)"
)
ARGUMENT_TOKEN_PATTERN = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
AGENT_LIST_QUERY_PATTERN = re.compile(
    r"\b(?:list|show|find|get|query)\b.*\b(?:agents|collectors|clients)\b"
)
AGENT_NOUN_PATTERN = re.compile(r"\b(?:agent|agents|collector|collectors|client|clients)\b")


class RuleFirstPlanner:
    """Deterministic fallback planner when LLM planning is unavailable."""

    async def plan(self, *, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Create a tool-constrained plan using deterministic keyword rules."""
        tool_names = [str(tool.get("name", "")).strip() for tool in tools]
        tool_lookup = {
            str(tool.get("name", "")).strip(): tool
            for tool in tools
            if str(tool.get("name", "")).strip()
        }
        normalized = text.strip().lower()
        parts = text.split()
        target = parts[-1] if len(parts) > 1 else None

        direct_tool = _find_direct_tool_request(text=text, tool_names=tool_names)
        if direct_tool is not None:
            direct_args = _extract_tool_arguments(
                text=text,
                tool_name=direct_tool,
                tool=tool_lookup.get(direct_tool),
                scoped_to_direct_invocation=True,
            )
            if not direct_args:
                direct_target = _extract_direct_target(text=text, tool_name=direct_tool)
                if direct_target:
                    direct_args = {"target": direct_target}
            requires_confirmation = any(
                keyword in direct_tool.lower()
                for keyword in ("restart", "delete", "remove", "shutdown")
            )
            return {
                RESPONSE_TEXT_KEY: "",
                TOOL_NAME_KEY: direct_tool,
                TOOL_ARGS_KEY: direct_args,
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
                    "`/opamp config collector-a`, or filter agents with "
                    "`/opamp tool_otel_agents host_name=alpha-node client_version=1.2.3`."
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

        otel_agents_tool = _find_otel_agents_tool_name(tool_names)
        if otel_agents_tool and _looks_like_agent_list_query(text):
            return {
                RESPONSE_TEXT_KEY: "",
                TOOL_NAME_KEY: otel_agents_tool,
                TOOL_ARGS_KEY: _extract_tool_arguments(
                    text=text,
                    tool_name=otel_agents_tool,
                    tool=tool_lookup.get(otel_agents_tool),
                    scoped_to_direct_invocation=False,
                ),
                REQUIRES_CONFIRMATION_KEY: False,
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


def _find_otel_agents_tool_name(tool_names: list[str]) -> str | None:
    """Return the best discovered tool name for listing/filtering agents."""
    for name in tool_names:
        if "otel_agents" in name.lower():
            return name
    for name in tool_names:
        lowered = name.lower()
        if "agent" in lowered and "tool" in lowered:
            return name
    return None


def _looks_like_agent_list_query(text: str) -> bool:
    """Determine whether free text likely intends an agent listing/filter request."""
    normalized = text.strip().lower()
    if not normalized:
        return False
    if normalized in {"agents", "collectors", "clients"}:
        return True
    if AGENT_LIST_QUERY_PATTERN.search(normalized):
        return True
    return bool(AGENT_NOUN_PATTERN.search(normalized) and ARGUMENT_KEY_VALUE_PATTERN.search(text))


def _extract_tool_arguments(
    *,
    text: str,
    tool_name: str,
    tool: dict[str, Any] | None,
    scoped_to_direct_invocation: bool,
) -> dict[str, Any]:
    """Extract schema-aware tool arguments from user text.

    Arguments are accepted as ``key=value`` (or ``key:value``) tokens and only
    mapped when they match the discovered tool schema. This keeps rule-first
    behavior aligned with the currently available tool options.
    """
    scope_text = text
    if scoped_to_direct_invocation:
        invocation_pattern = re.compile(rf"^\s*{re.escape(tool_name)}\b", re.IGNORECASE)
        match = invocation_pattern.search(scope_text)
        if not match:
            return {}
        scope_text = scope_text[match.end():]
    scope_text = scope_text.strip()
    if not scope_text:
        return {}

    properties = _extract_input_schema_properties(tool)
    parsed = _extract_key_value_arguments(scope_text, properties)

    if "invert_filter" in properties and "invert_filter" not in parsed:
        lowered_scope = scope_text.lower()
        if re.search(r"\bexclude\b", lowered_scope):
            parsed["invert_filter"] = True
        elif parsed and re.search(r"\bshow\b", lowered_scope):
            parsed["invert_filter"] = False

    if not parsed and "target" in properties:
        positional_target = _extract_first_positional_token(scope_text)
        if positional_target:
            parsed["target"] = positional_target
    return parsed


def _extract_input_schema_properties(tool: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return normalized ``inputSchema.properties`` mapping for a tool."""
    if not isinstance(tool, dict):
        return {}
    input_schema = tool.get("inputSchema")
    if not isinstance(input_schema, dict):
        return {}
    raw_properties = input_schema.get("properties")
    if not isinstance(raw_properties, dict):
        return {}
    properties: dict[str, dict[str, Any]] = {}
    for key, value in raw_properties.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        properties[key_text] = value if isinstance(value, dict) else {}
    return properties


def _extract_key_value_arguments(
    text: str,
    properties: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Extract ``key=value`` tokens and coerce values using schema metadata."""
    parsed: dict[str, Any] = {}
    for match in ARGUMENT_KEY_VALUE_PATTERN.finditer(text):
        raw_key = str(match.group("key") or "").strip().lstrip("-")
        raw_value = _strip_wrapping_quotes(str(match.group("value") or "").strip())
        if not raw_key or not raw_value:
            continue
        resolved_key = _resolve_argument_key(raw_key, properties)
        if resolved_key is None:
            if properties:
                continue
            resolved_key = raw_key
        parsed[resolved_key] = _coerce_argument_value(
            raw_value,
            properties.get(resolved_key, {}),
        )
    return parsed


def _resolve_argument_key(raw_key: str, properties: dict[str, dict[str, Any]]) -> str | None:
    """Resolve a user-provided argument name to one schema property key."""
    if not properties:
        return raw_key

    normalized_lookup = {
        _normalize_argument_name(name): name
        for name in properties
        if _normalize_argument_name(name)
    }
    normalized_key = _normalize_argument_name(raw_key)
    if not normalized_key:
        return None
    if normalized_key in normalized_lookup:
        return normalized_lookup[normalized_key]

    suffix_matches = {
        name
        for normalized_name, name in normalized_lookup.items()
        if normalized_name.endswith(normalized_key)
        or normalized_key.endswith(normalized_name)
    }
    if len(suffix_matches) == 1:
        return next(iter(suffix_matches))
    return None


def _normalize_argument_name(value: str) -> str:
    """Normalize argument names for forgiving matching across separators/casing."""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def _strip_wrapping_quotes(value: str) -> str:
    """Remove one pair of matching leading/trailing quotes."""
    stripped = value.strip()
    if len(stripped) < 2:
        return stripped
    if (
        (stripped.startswith('"') and stripped.endswith('"'))
        or (stripped.startswith("'") and stripped.endswith("'"))
    ):
        return stripped[1:-1]
    return stripped


def _coerce_argument_value(raw_value: str, schema: dict[str, Any]) -> Any:
    """Coerce user text to primitive schema type when safe."""
    arg_type = str(schema.get("type", "")).strip().lower() if schema else ""
    if arg_type == "boolean":
        normalized = raw_value.strip().lower()
        if normalized in BOOLEAN_TRUE_VALUES:
            return True
        if normalized in BOOLEAN_FALSE_VALUES:
            return False
        return raw_value
    if arg_type == "integer":
        try:
            return int(raw_value, 10)
        except ValueError:
            return raw_value
    if arg_type == "number":
        try:
            return float(raw_value)
        except ValueError:
            return raw_value
    return raw_value


def _extract_first_positional_token(text: str) -> str | None:
    """Return first non-key=value token from a command tail."""
    for token in ARGUMENT_TOKEN_PATTERN.findall(text):
        candidate = _strip_wrapping_quotes(token.strip())
        if not candidate:
            continue
        if ARGUMENT_KEY_VALUE_PATTERN.fullmatch(candidate):
            continue
        if "=" in candidate or ":" in candidate:
            continue
        return candidate
    return None
