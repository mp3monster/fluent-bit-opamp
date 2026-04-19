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

"""Blueprint routes for /tool endpoints.

References:
- FastMCP tool decorator documentation (`@mcp.tool` / `@mcpserver.tool`):
  https://gofastmcp.com/servers/tools
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from google.protobuf import text_format
from quart import Blueprint, Response, jsonify, request

from opamp_provider import config as provider_config
from opamp_provider.command_queue import (
    QueueCommandRequestError,
    build_custom_command_mcp_error_payload,
    queue_custom_command_from_mcp,
)
from opamp_provider.commands import get_command_metadata
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import ClientRecord, STORE
from opamp_provider.tool_api_contract import (
    OTEL_AGENTS_QUERY_PARAM_AGENT_DESCRIPTION,
    OTEL_AGENTS_QUERY_PARAM_CLIENT_ID,
    OTEL_AGENTS_QUERY_PARAM_CLIENT_VERSION,
    OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_BEFORE,
    OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_SINCE,
    OTEL_AGENTS_QUERY_PARAM_HOST_IP,
    OTEL_AGENTS_QUERY_PARAM_HOST_NAME,
    OTEL_AGENTS_QUERY_PARAM_INVERT_FILTER,
    OTEL_AGENTS_QUERY_PARAM_SERVICE_INSTANCE_ID,
    OTEL_AGENTS_QUERY_PARAM_MDISCONNECTED,
    OTEL_AGENTS_QUERY_PARAM_SUPPORTS_COMMAND_NAME,
    apply_otel_agents_openapi_contract,
)
from shared.opamp_config import anyvalue_to_string

mcptool_blueprint = Blueprint("mcptool", __name__)
mcpserver = FastMCP("OpAMP Server")
MODEL_DUMP_MODE = "json"  # Pydantic model_dump mode used for MCP/HTTP JSON responses.
logger = logging.getLogger(__name__)
# MCP tool decorators below register Python callables as MCP-invocable tools.
QUERY_PARAM_AGENT_DESCRIPTION = OTEL_AGENTS_QUERY_PARAM_AGENT_DESCRIPTION
QUERY_PARAM_CLIENT_ID = OTEL_AGENTS_QUERY_PARAM_CLIENT_ID
QUERY_PARAM_COMMUNICATION_BEFORE = OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_BEFORE
QUERY_PARAM_COMMUNICATION_SINCE = OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_SINCE
QUERY_PARAM_CLIENT_VERSION = OTEL_AGENTS_QUERY_PARAM_CLIENT_VERSION
QUERY_PARAM_MDISCONNECTED = OTEL_AGENTS_QUERY_PARAM_MDISCONNECTED
QUERY_PARAM_SUPPORTS_COMMAND_NAME = OTEL_AGENTS_QUERY_PARAM_SUPPORTS_COMMAND_NAME
QUERY_PARAM_SERVICE_INSTANCE_ID = OTEL_AGENTS_QUERY_PARAM_SERVICE_INSTANCE_ID
QUERY_PARAM_HOST_NAME = OTEL_AGENTS_QUERY_PARAM_HOST_NAME
QUERY_PARAM_HOST_IP = OTEL_AGENTS_QUERY_PARAM_HOST_IP
QUERY_PARAM_INVERT_FILTER = OTEL_AGENTS_QUERY_PARAM_INVERT_FILTER
AGENT_DESCRIPTION_HOST_NAME_KEY = "host.name"
AGENT_DESCRIPTION_HOST_IP_KEY = "host.ip"
DATE_TIME_SUFFIX_Z = "Z"
DATE_TIME_UTC_OFFSET = "+00:00"
BOOLEAN_TRUE_VALUES = {"1", "true", "yes", "on"}
BOOLEAN_FALSE_VALUES = {"0", "false", "no", "off"}
COMMAND_KEY_CLASSIFIER = "classifier"
COMMAND_KEY_OPERATION = "operation"
COMMAND_KEY_FQDN = "fqdn"
COMMAND_KEY_DISPLAY_NAME = "displayname"
COMMAND_CLASSIFIER_CUSTOM = "custom"
STANDARD_COMMAND_OPERATION_TO_CAPABILITY = {
    "restart": "accepts restart command",
}
ERROR_INVALID_BOOLEAN_FILTER = (
    "invalid boolean query parameter '%s'; expected one of: true, false, 1, 0, yes, no, on, off"
)
ERROR_INVALID_DATETIME_FILTER = (
    "invalid datetime query parameter '%s'; expected ISO-8601 value"
)
AGENT_DESCRIPTION_ATTRIBUTE_SPLIT_PATTERN = r"[,\s]+"
AGENT_DESCRIPTION_CACHE_SIZE = 512


def _normalize_query_text(value: str | None) -> str | None:
    """Return stripped query text or None when empty/unset."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _parse_optional_bool(value: str | bool | None, *, parameter_name: str) -> bool | None:
    """Parse a bool-like query value into `bool | None`."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized in BOOLEAN_TRUE_VALUES:
        return True
    if normalized in BOOLEAN_FALSE_VALUES:
        return False
    raise ValueError(ERROR_INVALID_BOOLEAN_FILTER % parameter_name)


def _as_utc(value: datetime) -> datetime:
    """Normalize datetime values into timezone-aware UTC timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_optional_datetime(value: str | None, *, parameter_name: str) -> datetime | None:
    """Parse an optional ISO-8601 query value into UTC datetime."""
    normalized = _normalize_query_text(value)
    if normalized is None:
        return None
    if normalized.endswith(DATE_TIME_SUFFIX_Z):
        normalized = f"{normalized[:-1]}{DATE_TIME_UTC_OFFSET}"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(ERROR_INVALID_DATETIME_FILTER % parameter_name) from exc
    return _as_utc(parsed)


def _matches_text(value: str | None, query: str | None) -> bool:
    """Return True when query is unset or is a case-insensitive substring match."""
    if query is None:
        return True
    if not value:
        return False
    return query.lower() in value.lower()


def _any_matches_text(values: list[str] | tuple[str, ...], query: str | None) -> bool:
    """Return True when any value matches query (case-insensitive substring)."""
    if query is None:
        return True
    needle = query.lower()
    for value in values:
        if needle in str(value).lower():
            return True
    return False


@lru_cache(maxsize=AGENT_DESCRIPTION_CACHE_SIZE)
def _parse_agent_description_attributes(
    agent_description: str,
) -> dict[str, tuple[str, ...]]:
    """Parse AgentDescription text and return key -> tuple(values) mapping."""
    desc = opamp_pb2.AgentDescription()
    text_format.Parse(agent_description, desc)
    collected: dict[str, list[str]] = {}
    for item in [*desc.identifying_attributes, *desc.non_identifying_attributes]:
        key = str(item.key).strip()
        value = anyvalue_to_string(item.value)
        if not key or value is None:
            continue
        collected.setdefault(key, []).append(value)
    return {key: tuple(values) for key, values in collected.items()}


def _record_agent_description_attributes(record: ClientRecord) -> dict[str, tuple[str, ...]]:
    """Read parsed agent-description attributes for one client record."""
    if not record.agent_description:
        return {}
    try:
        return _parse_agent_description_attributes(record.agent_description)
    except text_format.ParseError:
        logger.debug(
            "unable to parse agent_description for client_id=%s",
            record.client_id,
            exc_info=True,
        )
        return {}


def _record_host_names(record: ClientRecord) -> tuple[str, ...]:
    """Return host.name values extracted from agent description."""
    attributes = _record_agent_description_attributes(record)
    return attributes.get(AGENT_DESCRIPTION_HOST_NAME_KEY, ())


def _record_service_instance_ids(record: ClientRecord) -> tuple[str, ...]:
    """Return service-instance display-name candidates for filtering."""
    attributes = _record_agent_description_attributes(record)
    candidates: list[str] = list(attributes.get("service.instance.id", ()))
    if not candidates and record.client_id:
        candidates.append(record.client_id)
    seen: set[str] = set()
    deduped: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return tuple(deduped)


def _record_host_ips(record: ClientRecord) -> tuple[str, ...]:
    """Return host IP candidates from remote_addr and agent description fields."""
    candidates: list[str] = []
    if record.remote_addr:
        candidates.append(record.remote_addr)
    attributes = _record_agent_description_attributes(record)
    for raw in attributes.get(AGENT_DESCRIPTION_HOST_IP_KEY, ()):
        stripped = str(raw).strip().strip("[]")
        if not stripped:
            continue
        for part in re.split(AGENT_DESCRIPTION_ATTRIBUTE_SPLIT_PATTERN, stripped):
            normalized = part.strip()
            if normalized:
                candidates.append(normalized)
    seen: set[str] = set()
    deduped: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return tuple(deduped)


@lru_cache(maxsize=64)
def _matching_command_records(command_name: str) -> list[dict[str, str]]:
    """Find command metadata rows matching a user-provided command query string."""
    needle = command_name.lower()
    matches: list[dict[str, str]] = []
    for command in _list_all_commands_payload().get("commands", []):
        classifier = str(command.get(COMMAND_KEY_CLASSIFIER, "")).strip().lower()
        operation = str(command.get(COMMAND_KEY_OPERATION, "")).strip().lower()
        fqdn = str(command.get(COMMAND_KEY_FQDN, "")).strip().lower()
        display_name = str(command.get(COMMAND_KEY_DISPLAY_NAME, "")).strip().lower()
        if not any(
            needle in candidate
            for candidate in (operation, fqdn, display_name)
            if candidate
        ):
            continue
        matches.append(
            {
                COMMAND_KEY_CLASSIFIER: classifier,
                COMMAND_KEY_OPERATION: operation,
                COMMAND_KEY_FQDN: fqdn,
                COMMAND_KEY_DISPLAY_NAME: display_name,
            }
        )
    return matches


def _record_supports_command(record: ClientRecord, command_name: str | None) -> bool:
    """Return whether a client appears to support at least one named command."""
    if command_name is None:
        return True
    matches = _matching_command_records(command_name)
    capability_names = {
        str(value).strip().lower()
        for value in record.capabilities
        if str(value).strip()
    }
    custom_capabilities = {
        str(value).strip().lower()
        for value in record.custom_capabilities_reported
        if str(value).strip()
    }
    if not matches:
        return _any_matches_text(
            list(capability_names) + list(custom_capabilities),
            command_name,
        )
    for command in matches:
        classifier = command.get(COMMAND_KEY_CLASSIFIER, "")
        operation = command.get(COMMAND_KEY_OPERATION, "")
        if classifier == COMMAND_CLASSIFIER_CUSTOM:
            fqdn = command.get(COMMAND_KEY_FQDN, "")
            if fqdn and fqdn in custom_capabilities:
                return True
            if operation and operation in custom_capabilities:
                return True
            continue
        required_capability = STANDARD_COMMAND_OPERATION_TO_CAPABILITY.get(operation)
        if required_capability and required_capability in capability_names:
            return True
    return False


def _client_matches_otel_agents_filters(
    client: ClientRecord,
    *,
    agent_description: str | None,
    client_id: str | None,
    communication_before: datetime | None,
    communication_since: datetime | None,
    client_version: str | None,
    mdisconnected: bool | None,
    supports_command_name: str | None,
    service_instance_id: str | None,
    host_name: str | None,
    host_ip: str | None,
    invert_filter: bool,
    has_active_filters: bool,
) -> bool:
    """Evaluate whether one client satisfies requested /tool/otelAgents filters."""
    matches = True
    if mdisconnected is None:
        if client.disconnected:
            matches = False
    elif client.disconnected is not mdisconnected:
        matches = False

    if not _matches_text(client.agent_description, agent_description):
        matches = False
    if not _matches_text(client.client_id, client_id):
        matches = False
    if not _matches_text(client.client_version, client_version):
        matches = False
    if not _any_matches_text(_record_service_instance_ids(client), service_instance_id):
        matches = False
    if not _any_matches_text(_record_host_names(client), host_name):
        matches = False
    if not _any_matches_text(_record_host_ips(client), host_ip):
        matches = False
    if not _record_supports_command(client, supports_command_name):
        matches = False

    if communication_before is not None:
        if client.last_communication is None:
            matches = False
        elif _as_utc(client.last_communication) >= communication_before:
            matches = False
    if communication_since is not None:
        if client.last_communication is None:
            matches = False
        elif _as_utc(client.last_communication) <= communication_since:
            matches = False
    if invert_filter and has_active_filters:
        return not matches
    return matches


def _list_connected_otel_agents_payload(
    *,
    agent_description: str | None = None,
    client_id: str | None = None,
    communication_before: str | None = None,
    communication_since: str | None = None,
    client_version: str | None = None,
    mdisconnected: str | bool | None = None,
    supports_command_name: str | None = None,
    service_instance_id: str | None = None,
    host_name: str | None = None,
    host_ip: str | None = None,
    invert_filter: str | bool | None = None,
) -> dict[str, Any]:
    """Build the connected otel agents payload shared by HTTP and MCP tools."""
    normalized_agent_description = _normalize_query_text(agent_description)
    normalized_client_id = _normalize_query_text(client_id)
    normalized_client_version = _normalize_query_text(client_version)
    normalized_supports_command_name = _normalize_query_text(supports_command_name)
    normalized_service_instance_id = _normalize_query_text(service_instance_id)
    normalized_host_name = _normalize_query_text(host_name)
    normalized_host_ip = _normalize_query_text(host_ip)
    parsed_mdisconnected = _parse_optional_bool(
        mdisconnected,
        parameter_name=QUERY_PARAM_MDISCONNECTED,
    )
    parsed_invert_filter = _parse_optional_bool(
        invert_filter,
        parameter_name=QUERY_PARAM_INVERT_FILTER,
    )
    parsed_communication_before = _parse_optional_datetime(
        communication_before,
        parameter_name=QUERY_PARAM_COMMUNICATION_BEFORE,
    )
    parsed_communication_since = _parse_optional_datetime(
        communication_since,
        parameter_name=QUERY_PARAM_COMMUNICATION_SINCE,
    )
    has_active_filters = any(
        value is not None
        for value in (
            normalized_agent_description,
            normalized_client_id,
            parsed_communication_before,
            parsed_communication_since,
            normalized_client_version,
            parsed_mdisconnected,
            normalized_supports_command_name,
            normalized_service_instance_id,
            normalized_host_name,
            normalized_host_ip,
        )
    )
    agents = [
        client.model_dump_for_otel_agents_tool()
        for client in STORE.list()
        if _client_matches_otel_agents_filters(
            client,
            agent_description=normalized_agent_description,
            client_id=normalized_client_id,
            communication_before=parsed_communication_before,
            communication_since=parsed_communication_since,
            client_version=normalized_client_version,
            mdisconnected=parsed_mdisconnected,
            supports_command_name=normalized_supports_command_name,
            service_instance_id=normalized_service_instance_id,
            host_name=normalized_host_name,
            host_ip=normalized_host_ip,
            invert_filter=parsed_invert_filter is True,
            has_active_filters=has_active_filters,
        )
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
    """Load the OpenAPI specification payload shared by HTTP and MCP tools."""
    return _load_tool_openapi_spec_payload()


@lru_cache(maxsize=1)
def _load_tool_openapi_spec_payload() -> dict[str, Any]:
    """Read cached OpenAPI template and inject shared otel-agent contract schemas."""
    spec_path = Path(__file__).with_name("tool_openapi_spec.json")
    with spec_path.open("r", encoding="utf-8") as spec_file:
        spec = json.load(spec_file)
    return apply_otel_agents_openapi_contract(spec)


@mcptool_blueprint.get("/tool/otelAgents")
async def list_connected_otel_agents() -> Response:
    """List agents with optional query filters (connected-only by default)."""
    try:
        payload = _list_connected_otel_agents_payload(
            agent_description=request.args.get(QUERY_PARAM_AGENT_DESCRIPTION),
            client_id=request.args.get(QUERY_PARAM_CLIENT_ID),
            communication_before=request.args.get(QUERY_PARAM_COMMUNICATION_BEFORE),
            communication_since=request.args.get(QUERY_PARAM_COMMUNICATION_SINCE),
            client_version=request.args.get(QUERY_PARAM_CLIENT_VERSION),
            mdisconnected=request.args.get(QUERY_PARAM_MDISCONNECTED),
            supports_command_name=request.args.get(QUERY_PARAM_SUPPORTS_COMMAND_NAME),
            service_instance_id=request.args.get(QUERY_PARAM_SERVICE_INSTANCE_ID),
            host_name=request.args.get(QUERY_PARAM_HOST_NAME),
            host_ip=request.args.get(QUERY_PARAM_HOST_IP),
            invert_filter=request.args.get(QUERY_PARAM_INVERT_FILTER),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


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
    description=(
        "Return OpAMP agents with optional filters. "
        "By default, this lists only agents that are not disconnected."
    ),
)
def mcp_tool_otel_agents(
    agent_description: str | None = None,
    client_id: str | None = None,
    communication_before: str | None = None,
    communication_since: str | None = None,
    client_version: str | None = None,
    mdisconnected: bool | str | None = None,
    supports_command_name: str | None = None,
    service_instance_id: str | None = None,
    host_name: str | None = None,
    host_ip: str | None = None,
    invert_filter: bool | str | None = None,
) -> dict[str, Any]:
    """Expose connected otel agents through MCP."""
    try:
        return _list_connected_otel_agents_payload(
            agent_description=agent_description,
            client_id=client_id,
            communication_before=communication_before,
            communication_since=communication_since,
            client_version=client_version,
            mdisconnected=mdisconnected,
            supports_command_name=supports_command_name,
            service_instance_id=service_instance_id,
            host_name=host_name,
            host_ip=host_ip,
            invert_filter=invert_filter,
        )
    except ValueError as exc:
        return {"error": str(exc)}


@mcpserver.tool(
    name="tool_commands",
    description="Return all available OpAMP commands, both custom and standard.",
)
def mcp_tool_commands() -> dict[str, Any]:
    """Expose full command catalog through MCP."""
    return _list_all_commands_payload()


@mcpserver.tool(
    name="tool_invoke_custom_command",
    description=(
        "Queue a custom command for a specific OpAMP client. "
        "Returns a friendly validation error payload when request fields are invalid."
    ),
)
def mcp_tool_invoke_custom_command(
    client_id: str,
    operation: str,
    capability: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Queue one custom command from MCP by validating and normalizing user input."""
    try:
        cmd = queue_custom_command_from_mcp(
            client_id=client_id,
            operation=operation,
            capability=capability,
            parameters=parameters,
            store=STORE,
            max_events=provider_config.CONFIG.client_event_history_size,
            logger=logger,
        )
    except QueueCommandRequestError as exc:
        return build_custom_command_mcp_error_payload(exc)

    return {
        "status": "queued",
        "client_id": client_id,
        "classifier": cmd.classifier,
        "action": cmd.action,
        "command": cmd.model_dump(mode=MODEL_DUMP_MODE),
    }
