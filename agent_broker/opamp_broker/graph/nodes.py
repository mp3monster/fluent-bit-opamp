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
from typing import Any, Final

try:
    import pandas as pd
except Exception:  # pragma: no cover - fallback for minimal runtime environments.
    pd = None  # type: ignore[assignment]

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

# Tool response payload keys.
PAYLOAD_KEY_ACTION: Final[str] = "action"
PAYLOAD_KEY_AGENT_ID: Final[str] = "agent_id"
PAYLOAD_KEY_AGENTS: Final[str] = "agents"
PAYLOAD_KEY_CLASSIFIER: Final[str] = "classifier"
PAYLOAD_KEY_CLIENT_ID: Final[str] = "client_id"
PAYLOAD_KEY_COMMANDS: Final[str] = "commands"
PAYLOAD_KEY_CONTENT: Final[str] = "content"
PAYLOAD_KEY_DISPLAY_NAME: Final[str] = "displayname"
PAYLOAD_KEY_ERROR: Final[str] = "error"
PAYLOAD_KEY_ID: Final[str] = "id"
PAYLOAD_KEY_INSTANCE_ID: Final[str] = "instance_id"
PAYLOAD_KEY_NAME: Final[str] = "name"
PAYLOAD_KEY_OPERATION: Final[str] = "operation"
PAYLOAD_KEY_OPENAPI_SPEC: Final[str] = "openapi_spec"
PAYLOAD_KEY_PATHS: Final[str] = "paths"
PAYLOAD_KEY_STATUS: Final[str] = "status"
PAYLOAD_KEY_TEXT: Final[str] = "text"
PAYLOAD_KEY_TOTAL: Final[str] = "total"

PAYLOAD_STATUS_QUEUED: Final[str] = "queued"
UNKNOWN_CLIENT_LABEL: Final[str] = "unknown-client"
RESPONSE_PREVIEW_ITEM_LIMIT: Final[int] = 10
AGENT_TABLE_MAX_ROWS: Final[int] = RESPONSE_PREVIEW_ITEM_LIMIT
AGENT_LONG_DETAILS_MAX_ITEMS: Final[int] = AGENT_TABLE_MAX_ROWS
AGENT_DESCRIPTION_KEY_PREFIX: Final[str] = "key:"
AGENT_DESCRIPTION_STRING_VALUE_PREFIX: Final[str] = "string_value:"
AGENT_DESCRIPTION_BOOL_VALUE_PREFIX: Final[str] = "bool_value:"
AGENT_DESCRIPTION_INT_VALUE_PREFIX: Final[str] = "int_value:"
AGENT_DESCRIPTION_DOUBLE_VALUE_PREFIX: Final[str] = "double_value:"
AGENT_DESCRIPTION_BYTES_VALUE_PREFIX: Final[str] = "bytes_value:"
AGENT_FALLBACK_IP_KEY: Final[str] = "ip"
AGENT_FALLBACK_HOSTNAME_KEY: Final[str] = "hostname"
AGENT_FALLBACK_MAC_KEY: Final[str] = "mac_address"
AGENT_SOURCE_REMOTE_ADDR_KEY: Final[str] = "remote_addr"
AGENT_SOURCE_CLIENT_ID_KEY: Final[str] = "client_id"
AGENT_SOURCE_AGENT_DESCRIPTION_KEY: Final[str] = "agent_description"
OPENAPI_COMPONENTS_KEY: Final[str] = "components"
OPENAPI_SCHEMAS_KEY: Final[str] = "schemas"
OPENAPI_PROPERTIES_KEY: Final[str] = "properties"
OPENAPI_DESCRIPTION_KEY: Final[str] = "description"
OPENAPI_OTEL_AGENT_SCHEMA_KEY: Final[str] = "OtelAgent"
OPENAPI_PATHS_KEY: Final[str] = "paths"
OPENAPI_TOOL_OTEL_AGENTS_PATH_KEY: Final[str] = "/tool/otelAgents"
OPENAPI_GET_KEY: Final[str] = "get"
OPENAPI_RESPONSES_KEY: Final[str] = "responses"
OPENAPI_RESPONSE_200_KEY: Final[str] = "200"
OPENAPI_CONTENT_KEY: Final[str] = "content"
OPENAPI_APPLICATION_JSON_KEY: Final[str] = "application/json"
OPENAPI_SCHEMA_KEY: Final[str] = "schema"
OPENAPI_SCHEMA_REF_KEY: Final[str] = "$ref"
OPENAPI_REF_PREFIX: Final[str] = "#/components/schemas/"
MARKDOWN_BULLET: Final[str] = "- "

AGENT_LABEL_KEYS: Final[tuple[str, ...]] = (
    PAYLOAD_KEY_ID,
    PAYLOAD_KEY_NAME,
    PAYLOAD_KEY_AGENT_ID,
    PAYLOAD_KEY_INSTANCE_ID,
)
AGENT_TABLE_PRIORITY_COLUMNS: Final[tuple[str, ...]] = (
    PAYLOAD_KEY_ID,
    PAYLOAD_KEY_NAME,
    PAYLOAD_KEY_AGENT_ID,
    PAYLOAD_KEY_INSTANCE_ID,
    PAYLOAD_KEY_STATUS,
)
AGENT_SHORT_RICH_TEXT_FIELDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("service.name", ("service.name",)),
    ("service.type", ("service.type",)),
    ("service.instance.id", ("service.instance.id",)),
    ("service.version", ("service.version",)),
    ("os_type", ("os.type", "os_type")),
    ("os_version", ("os.version", "os_version")),
    ("hostname", ("host.name", AGENT_FALLBACK_HOSTNAME_KEY)),
    ("ip", ("host.ip", "ip", "ip_address", AGENT_SOURCE_REMOTE_ADDR_KEY)),
    ("mac_address", ("host.mac", "host.mac_address", AGENT_FALLBACK_MAC_KEY)),
)
AGENT_FIELD_DESCRIPTION_DEFAULTS: Final[dict[str, str]] = {
    "service.name": "Service name reported by the OpenTelemetry agent.",
    "service.type": "Service type/category for the running workload.",
    "service.instance.id": "Stable instance identifier for the running service.",
    "service.version": "Service version reported in agent identifying attributes.",
    "os.type": "Operating system family/type for the host environment.",
    "os.version": "Operating system version for the host environment.",
    "host.name": "Hostname reported by the agent.",
    "host.ip": "Primary host IP address reported by the agent.",
    "host.mac": "Primary host MAC address reported by the agent.",
    AGENT_SOURCE_CLIENT_ID_KEY: "Unique client identifier tracked by the provider.",
    AGENT_SOURCE_REMOTE_ADDR_KEY: "Last known source IP address observed by the provider.",
}
AGENT_CORE_DETAIL_FIELDS: Final[tuple[str, ...]] = (
    AGENT_SOURCE_CLIENT_ID_KEY,
    "service.name",
    "service.type",
    "service.instance.id",
    "service.version",
    "os.type",
    "os.version",
    "host.name",
    "host.ip",
    "host.mac",
    AGENT_SOURCE_REMOTE_ADDR_KEY,
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
    content = result.get(PAYLOAD_KEY_CONTENT)
    parsed_content = _parse_content_payload(content)

    if isinstance(parsed_content, dict):
        error = parsed_content.get(PAYLOAD_KEY_ERROR)
        if isinstance(error, str) and error.strip():
            return f"The tool `{tool_name}` returned an error: {error.strip()}"

        if PAYLOAD_KEY_AGENTS in parsed_content and isinstance(parsed_content[PAYLOAD_KEY_AGENTS], list):
            return _summarize_agents_payload(parsed_content)

        if PAYLOAD_KEY_COMMANDS in parsed_content and isinstance(parsed_content[PAYLOAD_KEY_COMMANDS], list):
            return _summarize_commands_payload(parsed_content)

        if PAYLOAD_KEY_PATHS in parsed_content and isinstance(parsed_content[PAYLOAD_KEY_PATHS], dict):
            return _summarize_openapi_payload(parsed_content)

        if str(parsed_content.get(PAYLOAD_KEY_STATUS, "")).strip().lower() == PAYLOAD_STATUS_QUEUED:
            return _summarize_queue_result(parsed_content)

        return _summarize_mapping(parsed_content)

    if isinstance(parsed_content, list):
        if not parsed_content:
            return "The tool returned an empty result."
        preview = ", ".join(
            str(item) for item in parsed_content[:RESPONSE_PREVIEW_ITEM_LIMIT]
        )
        suffix = (
            ""
            if len(parsed_content) <= RESPONSE_PREVIEW_ITEM_LIMIT
            else ", ..."
        )
        return f"The tool returned {len(parsed_content)} item(s): {preview}{suffix}"

    text = str(parsed_content).strip()
    if text:
        return text
    return "The tool completed, but did not return any output."


def _parse_content_payload(content: Any) -> Any:
    """Normalize MCP content payload without attempting JSON auto-parsing."""
    if isinstance(content, list):
        text_chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and PAYLOAD_KEY_TEXT in item:
                text_chunks.append(str(item.get(PAYLOAD_KEY_TEXT, "")))
            else:
                text_chunks.append(str(item))
        return " ".join(chunk for chunk in text_chunks if chunk.strip()).strip()
    if isinstance(content, str):
        return content
    if content is None:
        return {}
    return content


def _extract_agent_labels(agents: list[Any]) -> list[str]:
    labels: list[str] = []
    for agent in agents:
        if isinstance(agent, dict):
            for key in AGENT_LABEL_KEYS:
                value = agent.get(key)
                if value is not None and str(value).strip():
                    labels.append(str(value).strip())
                    break
        elif str(agent).strip():
            labels.append(str(agent).strip())
    return labels


def _summarize_agents_payload(payload: dict[str, Any]) -> str:
    agents_raw = payload.get(PAYLOAD_KEY_AGENTS, [])
    if not isinstance(agents_raw, list):
        return "I checked the agents list, but the payload was invalid."
    total_raw = payload.get(PAYLOAD_KEY_TOTAL)
    try:
        total = int(total_raw) if total_raw is not None else len(agents_raw)
    except (TypeError, ValueError):
        total = len(agents_raw)

    if total <= 0:
        return "I checked and found no OpenTelemetry agents."

    openapi_spec = payload.get(PAYLOAD_KEY_OPENAPI_SPEC)
    field_descriptions = _resolve_agent_field_descriptions(openapi_spec)
    short_rich_text = _render_agents_short_rich_text(agents_raw)
    detailed_rich_text = _render_agents_detailed_rich_text(
        agents_raw,
        field_descriptions=field_descriptions,
    )
    if short_rich_text or detailed_rich_text:
        shown = min(len(agents_raw), AGENT_TABLE_MAX_ROWS)
        suffix = (
            f"\nShowing first {shown} agent(s)."
            if total > shown or len(agents_raw) > shown
            else ""
        )
        sections: list[str] = []
        if short_rich_text:
            sections.append(f"Short view:\n{short_rich_text}")
        if detailed_rich_text:
            sections.append(f"Detailed view:\n{detailed_rich_text}")
        return (
            f"I found {total} OpenTelemetry agent(s).{suffix}\n\n"
            + "\n\n".join(sections)
        )

    labels = _extract_agent_labels(agents_raw)
    if labels:
        preview = ", ".join(labels[:AGENT_TABLE_MAX_ROWS])
        extra = "" if len(labels) <= AGENT_TABLE_MAX_ROWS else ", ..."
        return f"I found {total} OpenTelemetry agent(s): {preview}{extra}"
    return f"I found {total} OpenTelemetry agent(s)."


def _render_agents_short_rich_text(agents: list[Any]) -> str:
    rendered: list[str] = []
    for agent in agents[:AGENT_TABLE_MAX_ROWS]:
        if not isinstance(agent, dict):
            continue
        line = _render_agent_short_rich_text(agent)
        if line:
            rendered.append(f"{MARKDOWN_BULLET}{line}")
    return "\n".join(rendered)


def _render_agent_short_rich_text(agent: dict[str, Any]) -> str:
    values = _extract_agent_attribute_values(agent)
    parts: list[str] = []
    for label, candidates in AGENT_SHORT_RICH_TEXT_FIELDS:
        value = _first_non_empty_attribute(values, candidates)
        if value:
            parts.append(f"{label}={value}")
    if parts:
        return "; ".join(parts)
    fallback_label = _extract_agent_labels([agent])
    if fallback_label:
        return str(fallback_label[0])
    return ""


def _render_agent_short_rich_txt(agent: dict[str, Any]) -> str:
    """Compatibility alias using `rich_txt` naming for short agent rendering."""
    return _render_agent_short_rich_text(agent)


def _render_agents_detailed_rich_text(
    agents: list[Any],
    *,
    field_descriptions: dict[str, str],
) -> str:
    rendered: list[str] = []
    count = 0
    for agent in agents:
        if count >= AGENT_LONG_DETAILS_MAX_ITEMS:
            break
        if not isinstance(agent, dict):
            continue
        count += 1
        rendered.append(f"Agent {count}:")
        details = _render_agent_long_rich_text(
            agent,
            field_descriptions=field_descriptions,
        )
        if details:
            rendered.append(details)
    return "\n".join(rendered).strip()


def _render_agent_long_rich_text(
    agent: dict[str, Any],
    *,
    field_descriptions: dict[str, str],
) -> str:
    values = _extract_agent_attribute_values(agent)
    if not values:
        return f"{MARKDOWN_BULLET}No attributes reported."
    ordered_keys = _order_agent_attribute_keys(values)
    lines: list[str] = []
    for key in ordered_keys:
        raw_value = values.get(key)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value:
            continue
        description = field_descriptions.get(key, "").strip()
        if description:
            lines.append(f"{MARKDOWN_BULLET}`{key}`: `{value}` ({description})")
        else:
            lines.append(f"{MARKDOWN_BULLET}`{key}`: `{value}`")
    return "\n".join(lines)


def _render_agent_long_rich_txt(
    agent: dict[str, Any],
    *,
    field_descriptions: dict[str, str],
) -> str:
    """Compatibility alias using `rich_txt` naming for detailed rendering."""
    return _render_agent_long_rich_text(
        agent,
        field_descriptions=field_descriptions,
    )


def _order_agent_attribute_keys(values: dict[str, str]) -> list[str]:
    core_keys = [key for key in AGENT_CORE_DETAIL_FIELDS if key in values]
    remaining = sorted(
        key for key in values if key not in set(AGENT_CORE_DETAIL_FIELDS)
    )
    return core_keys + remaining


def _extract_agent_attribute_values(agent: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in agent.items():
        if str(key) == AGENT_SOURCE_AGENT_DESCRIPTION_KEY:
            continue
        if isinstance(value, (dict, list)):
            continue
        rendered = str(value).strip() if value is not None else ""
        if rendered:
            values[str(key)] = rendered

    description_attributes = _parse_agent_description_attributes(
        str(agent.get(AGENT_SOURCE_AGENT_DESCRIPTION_KEY, ""))
    )
    values.update(description_attributes)

    if AGENT_SOURCE_REMOTE_ADDR_KEY in values and AGENT_FALLBACK_IP_KEY not in values:
        values[AGENT_FALLBACK_IP_KEY] = values[AGENT_SOURCE_REMOTE_ADDR_KEY]
    if "host.name" in values and AGENT_FALLBACK_HOSTNAME_KEY not in values:
        values[AGENT_FALLBACK_HOSTNAME_KEY] = values["host.name"]
    if "host.mac" in values and AGENT_FALLBACK_MAC_KEY not in values:
        values[AGENT_FALLBACK_MAC_KEY] = values["host.mac"]
    return values


def _parse_agent_description_attributes(agent_description: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    if not agent_description.strip():
        return attributes

    current_key: str | None = None
    for raw_line in agent_description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key_match = re.search(r'key:\s*"([^"]+)"', line)
        if key_match:
            current_key = key_match.group(1).strip()
            inline_value = _extract_inline_proto_value(line)
            if current_key and inline_value:
                attributes[current_key] = inline_value
                current_key = None
            continue
        if not current_key:
            continue
        inline_value = _extract_inline_proto_value(line)
        if inline_value:
            attributes[current_key] = inline_value
            current_key = None
    return attributes


def _parse_proto_scalar(line: str) -> str:
    _, _, raw = line.partition(":")
    candidate = raw.strip()
    if candidate.startswith('"') and candidate.endswith('"') and len(candidate) >= 2:
        return candidate[1:-1]
    return candidate


def _extract_inline_proto_value(line: str) -> str:
    for prefix in (
        AGENT_DESCRIPTION_STRING_VALUE_PREFIX,
        AGENT_DESCRIPTION_BOOL_VALUE_PREFIX,
        AGENT_DESCRIPTION_INT_VALUE_PREFIX,
        AGENT_DESCRIPTION_DOUBLE_VALUE_PREFIX,
        AGENT_DESCRIPTION_BYTES_VALUE_PREFIX,
    ):
        marker_index = line.find(prefix)
        if marker_index < 0:
            continue
        candidate = line[marker_index + len(prefix):].strip()
        if not candidate:
            continue
        candidate = candidate.split("}", 1)[0].strip()
        candidate = candidate.split("{", 1)[0].strip()
        if candidate.startswith('"') and candidate.endswith('"') and len(candidate) >= 2:
            candidate = candidate[1:-1]
        if candidate:
            return candidate
    return ""


def _first_non_empty_attribute(
    values: dict[str, str],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _resolve_agent_field_descriptions(openapi_spec: Any) -> dict[str, str]:
    descriptions: dict[str, str] = dict(AGENT_FIELD_DESCRIPTION_DEFAULTS)
    schema_descriptions = _extract_agent_field_descriptions_from_spec(openapi_spec)
    descriptions.update(schema_descriptions)
    return descriptions


def _extract_agent_field_descriptions_from_spec(openapi_spec: Any) -> dict[str, str]:
    if not isinstance(openapi_spec, dict):
        return {}

    schema = _resolve_otel_agent_schema_from_spec(openapi_spec)
    if not isinstance(schema, dict):
        return {}
    properties = schema.get(OPENAPI_PROPERTIES_KEY)
    if not isinstance(properties, dict):
        return {}

    descriptions: dict[str, str] = {}
    for key, property_spec in properties.items():
        if not isinstance(property_spec, dict):
            continue
        description = str(property_spec.get(OPENAPI_DESCRIPTION_KEY, "")).strip()
        if description:
            descriptions[str(key)] = description
    return descriptions


def _resolve_otel_agent_schema_from_spec(openapi_spec: dict[str, Any]) -> dict[str, Any] | None:
    components = openapi_spec.get(OPENAPI_COMPONENTS_KEY)
    if not isinstance(components, dict):
        return None
    schemas = components.get(OPENAPI_SCHEMAS_KEY)
    if not isinstance(schemas, dict):
        return None

    direct_schema = schemas.get(OPENAPI_OTEL_AGENT_SCHEMA_KEY)
    if isinstance(direct_schema, dict):
        return direct_schema

    paths = openapi_spec.get(OPENAPI_PATHS_KEY)
    if not isinstance(paths, dict):
        return None
    otel_agents_path = paths.get(OPENAPI_TOOL_OTEL_AGENTS_PATH_KEY)
    if not isinstance(otel_agents_path, dict):
        return None
    get_operation = otel_agents_path.get(OPENAPI_GET_KEY)
    if not isinstance(get_operation, dict):
        return None
    responses = get_operation.get(OPENAPI_RESPONSES_KEY)
    if not isinstance(responses, dict):
        return None
    ok_response = responses.get(OPENAPI_RESPONSE_200_KEY)
    if not isinstance(ok_response, dict):
        return None
    content = ok_response.get(OPENAPI_CONTENT_KEY)
    if not isinstance(content, dict):
        return None
    app_json = content.get(OPENAPI_APPLICATION_JSON_KEY)
    if not isinstance(app_json, dict):
        return None
    schema = app_json.get(OPENAPI_SCHEMA_KEY)
    if not isinstance(schema, dict):
        return None
    schema_ref = str(schema.get(OPENAPI_SCHEMA_REF_KEY, "")).strip()
    if not schema_ref.startswith(OPENAPI_REF_PREFIX):
        return None
    schema_name = schema_ref[len(OPENAPI_REF_PREFIX):]
    response_schema = schemas.get(schema_name)
    if not isinstance(response_schema, dict):
        return None
    response_properties = response_schema.get(OPENAPI_PROPERTIES_KEY)
    if not isinstance(response_properties, dict):
        return None
    agents_property = response_properties.get(PAYLOAD_KEY_AGENTS)
    if not isinstance(agents_property, dict):
        return None
    items = agents_property.get("items")
    if not isinstance(items, dict):
        return None
    item_ref = str(items.get(OPENAPI_SCHEMA_REF_KEY, "")).strip()
    if not item_ref.startswith(OPENAPI_REF_PREFIX):
        return None
    item_schema_name = item_ref[len(OPENAPI_REF_PREFIX):]
    item_schema = schemas.get(item_schema_name)
    if isinstance(item_schema, dict):
        return item_schema
    return None


def _render_agents_table(agents: list[Any]) -> str | None:
    if pd is None:
        return None

    rows: list[dict[str, Any]] = []
    for agent in agents[:AGENT_TABLE_MAX_ROWS]:
        if isinstance(agent, dict):
            row = {
                str(key): _stringify_table_value(value)
                for key, value in agent.items()
            }
            if row:
                rows.append(row)
            continue
        label = str(agent).strip()
        if label:
            rows.append({PAYLOAD_KEY_NAME: label})

    if not rows:
        return None

    try:
        frame = pd.json_normalize(rows, sep=".").fillna("")
    except Exception:
        return None

    if frame.empty:
        return None
    ordered_columns = _ordered_agent_columns(list(frame.columns))
    return frame[ordered_columns].to_string(index=False)


def _ordered_agent_columns(columns: list[str]) -> list[str]:
    preferred = [col for col in AGENT_TABLE_PRIORITY_COLUMNS if col in columns]
    remaining = sorted(col for col in columns if col not in preferred)
    return preferred + remaining


def _stringify_table_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, sort_keys=True)
        except TypeError:
            return str(value)
    return value


def _summarize_commands_payload(payload: dict[str, Any]) -> str:
    commands_raw = payload.get(PAYLOAD_KEY_COMMANDS, [])
    if not isinstance(commands_raw, list):
        return "I checked the command catalog, but the payload was invalid."
    total_raw = payload.get(PAYLOAD_KEY_TOTAL)
    try:
        total = int(total_raw) if total_raw is not None else len(commands_raw)
    except (TypeError, ValueError):
        total = len(commands_raw)

    if total <= 0:
        return "I checked and found no available commands."

    labels = _extract_command_labels(commands_raw)
    if labels:
        preview = ", ".join(labels[:RESPONSE_PREVIEW_ITEM_LIMIT])
        suffix = "" if len(labels) <= RESPONSE_PREVIEW_ITEM_LIMIT else ", ..."
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
        display_name = str(command.get(PAYLOAD_KEY_DISPLAY_NAME, "")).strip()
        operation = str(command.get(PAYLOAD_KEY_OPERATION, "")).strip()
        classifier = str(command.get(PAYLOAD_KEY_CLASSIFIER, "")).strip()
        if display_name:
            labels.append(display_name)
        elif classifier and operation:
            labels.append(f"{classifier}/{operation}")
        elif operation:
            labels.append(operation)
    return labels


def _summarize_openapi_payload(payload: dict[str, Any]) -> str:
    paths_raw = payload.get(PAYLOAD_KEY_PATHS)
    if not isinstance(paths_raw, dict):
        return "I checked the OpenAPI spec, but no paths were available."
    routes = sorted(str(path).strip() for path in paths_raw if str(path).strip())
    total = len(routes)
    if total <= 0:
        return "I checked the OpenAPI spec, but it contains no routes."
    preview = ", ".join(routes[:RESPONSE_PREVIEW_ITEM_LIMIT])
    suffix = "" if len(routes) <= RESPONSE_PREVIEW_ITEM_LIMIT else ", ..."
    return f"I found {total} API route(s) in the OpenAPI spec: {preview}{suffix}."


def _summarize_queue_result(payload: dict[str, Any]) -> str:
    client_id = str(payload.get(PAYLOAD_KEY_CLIENT_ID, "")).strip() or UNKNOWN_CLIENT_LABEL
    classifier = str(payload.get(PAYLOAD_KEY_CLASSIFIER, "")).strip()
    action = str(payload.get(PAYLOAD_KEY_ACTION, "")).strip()
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
        tool_registry.get(name) or {PAYLOAD_KEY_NAME: name}
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

    target = chosen_args.get(STATE_KEY_TARGET)
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
        state[STATE_KEY_TOOL_RESULT] = {PAYLOAD_KEY_ERROR: str(exc)}
        state[STATE_KEY_RESPONSE_TEXT] = offline_message
        return state

    state[STATE_KEY_TOOL_RESULT] = result
    state[STATE_KEY_RESPONSE_TEXT] = _format_tool_response(str(tool_name), result)
    return state
