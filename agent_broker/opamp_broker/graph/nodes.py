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

"""Node implementations for normalization, intent classification, and execution.

The graph keeps each stage as a focused function so intermediate state is easy
to inspect and behavior can be extended without rewriting the full pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from opamp_broker.graph.state import (
    STATE_KEY_COMMAND,
    STATE_KEY_INTENT,
    STATE_KEY_NORMALIZED_TEXT,
    STATE_KEY_REQUIRES_CONFIRMATION,
    STATE_KEY_RESPONSE_TEXT,
    STATE_KEY_TARGET,
    STATE_KEY_TEXT,
    STATE_KEY_TOOL_ARGS,
    STATE_KEY_TOOL_NAME,
    STATE_KEY_TOOL_RESULT,
    STATE_KEY_TOOLS_AVAILABLE,
    BrokerState,
)
from opamp_broker.mcp.tools import MCPToolRegistry
from opamp_broker.mcp.client import MCPServerUnavailableError
from opamp_broker.planner.engine import (
    Planner,
    RESPONSE_TEXT_KEY,
    REQUIRES_CONFIRMATION_KEY,
    TOOL_ARGS_KEY,
    TOOL_NAME_KEY,
)
from opamp_broker.planner.rule_first_planner import RuleFirstPlanner

DEFAULT_MCP_SERVER_OFFLINE_MESSAGE = (
    "The OpAMP server is currently offline. Please try again shortly."
)
logger = logging.getLogger(__name__)


def _strip_bot_mention(text: str) -> str:
    """Remove Slack bot mention tokens from inbound text.

    Why this approach:
    mention tokens are transport noise that can degrade intent matching if not
    removed before normalization.

    Args:
        text: Raw message text from Slack events or slash commands.

    Returns:
        str: Text with ``<@...>`` mention fragments removed and stripped.
    """
    return re.sub(r"<@[^>]+>", "", text).strip()


def _format_tool_response(tool_name: str, result: dict[str, Any]) -> str:
    """Convert MCP tool output into a concise user-facing explanation."""
    content = result.get("content")
    parsed_content = _parse_content_payload(content)

    if isinstance(parsed_content, dict):
        error = parsed_content.get("error")
        if isinstance(error, str) and error.strip():
            return f"The tool `{tool_name}` returned an error: {error.strip()}"

        if "agents" in parsed_content and isinstance(parsed_content["agents"], list):
            agents = parsed_content["agents"]
            total_raw = parsed_content.get("total")
            try:
                total = int(total_raw) if total_raw is not None else len(agents)
            except (TypeError, ValueError):
                total = len(agents)
            if total <= 0:
                return "I checked and found no OpenTelemetry agents."
            names = _extract_agent_labels(agents)
            if names:
                return (
                    f"I found {total} OpenTelemetry agent(s): "
                    + ", ".join(names[:10])
                )
            return f"I found {total} OpenTelemetry agent(s)."

        if "commands" in parsed_content and isinstance(parsed_content["commands"], list):
            return _summarize_commands_payload(parsed_content)

        if "paths" in parsed_content and isinstance(parsed_content["paths"], dict):
            return _summarize_openapi_payload(parsed_content)

        if str(parsed_content.get("status", "")).strip().lower() == "queued":
            return _summarize_queue_result(parsed_content)

        return _summarize_mapping(parsed_content)

    if isinstance(parsed_content, list):
        if not parsed_content:
            return "The tool returned an empty result."
        preview = ", ".join(str(item) for item in parsed_content[:10])
        suffix = "" if len(parsed_content) <= 10 else ", ..."
        return f"The tool returned {len(parsed_content)} item(s): {preview}{suffix}"

    text = str(parsed_content).strip()
    if text:
        return text
    return "The tool completed, but did not return any output."


def _parse_content_payload(content: Any) -> Any:
    """Best-effort parse of MCP content payload into Python objects."""
    if isinstance(content, list):
        text_chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                text_chunks.append(str(item.get("text", "")))
            else:
                text_chunks.append(str(item))
        joined = " ".join(chunk for chunk in text_chunks if chunk.strip()).strip()
        parsed = _parse_json_if_possible(joined)
        return parsed if parsed is not None else joined
    if isinstance(content, str):
        parsed = _parse_json_if_possible(content)
        return parsed if parsed is not None else content
    if content is None:
        return {}
    return content


def _parse_json_if_possible(raw: str) -> Any | None:
    value = raw.strip()
    if not value:
        return None
    if not (value.startswith("{") or value.startswith("[")):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _extract_agent_labels(agents: list[Any]) -> list[str]:
    labels: list[str] = []
    for agent in agents:
        if isinstance(agent, dict):
            for key in ("id", "name", "agent_id", "instance_id"):
                value = agent.get(key)
                if value is not None and str(value).strip():
                    labels.append(str(value).strip())
                    break
        elif str(agent).strip():
            labels.append(str(agent).strip())
    return labels


def _summarize_commands_payload(payload: dict[str, Any]) -> str:
    commands_raw = payload.get("commands", [])
    if not isinstance(commands_raw, list):
        return "I checked the command catalog, but the payload was invalid."
    total_raw = payload.get("total")
    try:
        total = int(total_raw) if total_raw is not None else len(commands_raw)
    except (TypeError, ValueError):
        total = len(commands_raw)

    if total <= 0:
        return "I checked and found no available commands."

    labels = _extract_command_labels(commands_raw)
    if labels:
        preview = ", ".join(labels[:10])
        suffix = "" if len(labels) <= 10 else ", ..."
        return f"I found {total} available command(s): {preview}{suffix}."
    return f"I found {total} available command(s)."


def _extract_command_labels(commands: list[Any]) -> list[str]:
    labels: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            raw = str(command).strip()
            if raw:
                labels.append(raw)
            continue
        display_name = str(command.get("displayname", "")).strip()
        operation = str(command.get("operation", "")).strip()
        classifier = str(command.get("classifier", "")).strip()
        if display_name:
            labels.append(display_name)
        elif classifier and operation:
            labels.append(f"{classifier}/{operation}")
        elif operation:
            labels.append(operation)
    return labels


def _summarize_openapi_payload(payload: dict[str, Any]) -> str:
    paths_raw = payload.get("paths")
    if not isinstance(paths_raw, dict):
        return "I checked the OpenAPI spec, but no paths were available."
    routes = sorted(str(path).strip() for path in paths_raw if str(path).strip())
    total = len(routes)
    if total <= 0:
        return "I checked the OpenAPI spec, but it contains no routes."
    preview = ", ".join(routes[:10])
    suffix = "" if len(routes) <= 10 else ", ..."
    return f"I found {total} API route(s) in the OpenAPI spec: {preview}{suffix}."


def _summarize_queue_result(payload: dict[str, Any]) -> str:
    client_id = str(payload.get("client_id", "")).strip() or "unknown-client"
    classifier = str(payload.get("classifier", "")).strip()
    action = str(payload.get("action", "")).strip()
    if classifier and action:
        return (
            f"Queued command `{classifier}/{action}` for client `{client_id}`."
        )
    return f"Queued command for client `{client_id}`."


def _summarize_mapping(payload: dict[str, Any]) -> str:
    if not payload:
        return "The tool returned an empty result."
    pairs: list[str] = []
    for key, value in payload.items():
        key_name = str(key).strip() or "value"
        if isinstance(value, list):
            if not value:
                pairs.append(f"{key_name} is empty")
                continue
            if all(not isinstance(item, (dict, list)) for item in value):
                preview = ", ".join(str(item) for item in value[:5])
                suffix = "" if len(value) <= 5 else ", ..."
                pairs.append(
                    f"{key_name} has {len(value)} item(s): {preview}{suffix}"
                )
            else:
                pairs.append(f"{key_name} contains {len(value)} structured item(s)")
            continue
        if isinstance(value, dict):
            nested_keys = [str(nested).strip() for nested in value.keys()]
            preview = ", ".join(item for item in nested_keys[:5] if item)
            suffix = "" if len(nested_keys) <= 5 else ", ..."
            if preview:
                pairs.append(
                    f"{key_name} includes {len(nested_keys)} field(s): {preview}{suffix}"
                )
            else:
                pairs.append(f"{key_name} contains structured data")
            continue
        pairs.append(f"{key_name} is {value}")
    return "Tool result: " + "; ".join(pairs) + "."


def normalize_input(state: BrokerState) -> BrokerState:
    """Normalize user text into a canonical state field.

    Why this approach:
    collapsing whitespace and stripping mentions gives downstream nodes a stable
    representation for keyword matching.

    Args:
        state: Mutable broker state carrying inbound message text.

    Returns:
        BrokerState: Updated state containing normalized text.
    """
    text = _strip_bot_mention(state.get(STATE_KEY_TEXT, ""))
    normalized = " ".join(text.split()).strip()
    state[STATE_KEY_NORMALIZED_TEXT] = normalized
    return state


def classify_intent(state: BrokerState) -> BrokerState:
    """Classify message intent and whether explicit confirmation is required.

    Why this approach:
    destructive operations are conservatively flagged for confirmation while
    read-only status/help flows continue immediately.

    Args:
        state: Mutable broker state containing normalized user text.

    Returns:
        BrokerState: Updated state with command, intent, and confirmation flags.
    """
    text = state.get(STATE_KEY_NORMALIZED_TEXT, "").lower()
    parts = text.split()
    state[STATE_KEY_REQUIRES_CONFIRMATION] = False
    state[STATE_KEY_COMMAND] = parts[0] if parts else "help"

    if not text:
        state[STATE_KEY_INTENT] = "help"
    elif any(word in text for word in ["restart", "delete"]):
        state[STATE_KEY_INTENT] = "action"
        state[STATE_KEY_REQUIRES_CONFIRMATION] = True
    elif any(word in text for word in ["status", "health", "config", "tools", "help", "diff"]):
        state[STATE_KEY_INTENT] = "query"
    else:
        state[STATE_KEY_INTENT] = "diagnostic"
    return state


async def plan_action(
    state: BrokerState,
    tool_registry: MCPToolRegistry,
    planner: Planner,
    offline_message: str = DEFAULT_MCP_SERVER_OFFLINE_MESSAGE,
) -> BrokerState:
    """Use the runtime planner to map user text to a tool-constrained plan.

    Why this approach:
    planning is delegated to the LLM planner, but tool selection is validated
    against discovered MCP tools so execution remains strictly constrained.

    Args:
        state: Mutable broker state holding normalized user text.
        tool_registry: MCP registry providing discovered tool metadata.
        planner: Planner implementation (LLM or deterministic fallback).

    Returns:
        BrokerState: Updated state with response text and/or planned tool call.
    """
    text = state.get(STATE_KEY_NORMALIZED_TEXT, "")
    tool_names = tool_registry.list_names()
    if not tool_names:
        try:
            await tool_registry.refresh()
        except MCPServerUnavailableError as exc:
            logger.error(
                "MCP server unavailable during tool discovery: %s",
                exc,
                exc_info=True,
            )
            state[STATE_KEY_TOOLS_AVAILABLE] = []
            state[STATE_KEY_TOOL_NAME] = None
            state[STATE_KEY_TOOL_ARGS] = {}
            state[STATE_KEY_RESPONSE_TEXT] = offline_message
            return state
        except Exception:
            logger.exception("Unexpected error during MCP tool discovery refresh.")
        tool_names = tool_registry.list_names()

    tools = [
        tool_registry.get(name) or {"name": name}
        for name in tool_names
    ]

    state[STATE_KEY_TOOLS_AVAILABLE] = tool_names
    state[STATE_KEY_TOOL_NAME] = None
    state[STATE_KEY_TOOL_ARGS] = {}

    try:
        plan = await planner.plan(text=text, tools=tools)
    except Exception as exc:
        logger.exception(
            "Planner failed; falling back to rule-first planning. error=%s",
            exc,
        )
        try:
            plan = await RuleFirstPlanner().plan(text=text, tools=tools)
        except Exception:
            logger.exception("Fallback planner failed unexpectedly.")
            state[STATE_KEY_TOOL_NAME] = None
            state[STATE_KEY_TOOL_ARGS] = {}
            state[STATE_KEY_RESPONSE_TEXT] = (
                "I hit an internal planning issue. Please try again in a moment."
            )
            return state

    chosen_tool = plan.get(TOOL_NAME_KEY)
    if chosen_tool and chosen_tool not in tool_names:
        chosen_tool = None

    chosen_args = plan.get(TOOL_ARGS_KEY, {})
    if not isinstance(chosen_args, dict):
        chosen_args = {}
    if not chosen_tool:
        chosen_args = {}

    state[STATE_KEY_TOOL_NAME] = chosen_tool
    state[STATE_KEY_TOOL_ARGS] = chosen_args
    state[STATE_KEY_REQUIRES_CONFIRMATION] = bool(plan.get(REQUIRES_CONFIRMATION_KEY, False))

    response_text = plan.get(RESPONSE_TEXT_KEY, "")
    if isinstance(response_text, str) and response_text.strip():
        state[STATE_KEY_RESPONSE_TEXT] = response_text.strip()
    elif not chosen_tool:
        state[STATE_KEY_RESPONSE_TEXT] = (
            "I couldn't map that to a known MCP tool yet. "
            "Ask for `tools` to see what I discovered."
        )

    target = chosen_args.get("target")
    if target is None:
        parts = text.split()
        target = parts[-1] if len(parts) > 1 else None
    state[STATE_KEY_TARGET] = str(target) if target is not None else None
    return state


async def execute_or_summarize(
    state: BrokerState,
    tool_registry: MCPToolRegistry,
    offline_message: str = DEFAULT_MCP_SERVER_OFFLINE_MESSAGE,
) -> BrokerState:
    """Execute the selected tool call or produce a user-facing fallback message.

    Why this approach:
    this node centralizes final response rendering so all branches return a
    consistent ``response_text`` contract for Slack handlers.

    Args:
        state: Mutable broker state with planning outputs.
        tool_registry: MCP registry used to execute the selected tool.

    Returns:
        BrokerState: Updated state containing tool results and response text.
    """
    tool_name = state.get(STATE_KEY_TOOL_NAME)
    if not tool_name:
        if STATE_KEY_RESPONSE_TEXT not in state:
            state[STATE_KEY_RESPONSE_TEXT] = (
                "I couldn't map that to a known MCP tool yet. "
                "Ask for `tools` to see what I discovered."
            )
        return state

    if state.get(STATE_KEY_REQUIRES_CONFIRMATION):
        target = state.get(STATE_KEY_TARGET)
        state[STATE_KEY_RESPONSE_TEXT] = (
            f"I can run `{tool_name}` for `{target}` but I need confirmation first. "
            "Reply with `confirm` or `cancel`."
        )
        return state

    try:
        result = await tool_registry.call_tool(
            tool_name,
            state.get(STATE_KEY_TOOL_ARGS, {}),
        )
    except MCPServerUnavailableError as exc:
        logger.error(
            "MCP server unavailable while calling tool %s: %s",
            tool_name,
            exc,
            exc_info=True,
        )
        state[STATE_KEY_TOOL_RESULT] = {"error": str(exc)}
        state[STATE_KEY_RESPONSE_TEXT] = offline_message
        return state

    state[STATE_KEY_TOOL_RESULT] = result
    state[STATE_KEY_RESPONSE_TEXT] = _format_tool_response(str(tool_name), result)
    return state
