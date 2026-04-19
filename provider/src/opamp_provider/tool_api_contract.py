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

"""Shared API contract definitions used by provider payload exports and OpenAPI assembly.

Why this module exists:
the `/tool/otelAgents` payload shape must stay stable for MCP/HTTP consumers.
Keeping the contract in one place allows both serialization and OpenAPI output to
depend on the same definition, reducing schema drift.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Final

OTEL_AGENT_SCHEMA_NAME: Final[str] = "OtelAgent"
OTEL_AGENTS_RESPONSE_SCHEMA_NAME: Final[str] = "OtelAgentsResponse"
OTEL_AGENT_SCHEMA_REF: Final[str] = f"#/components/schemas/{OTEL_AGENT_SCHEMA_NAME}"
OTEL_AGENTS_RESPONSE_SCHEMA_REF: Final[str] = (
    f"#/components/schemas/{OTEL_AGENTS_RESPONSE_SCHEMA_NAME}"
)
OTEL_AGENTS_QUERY_PARAM_AGENT_DESCRIPTION: Final[str] = "agent_description"
OTEL_AGENTS_QUERY_PARAM_CLIENT_ID: Final[str] = "client_id"
OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_BEFORE: Final[str] = "communication_before"
OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_SINCE: Final[str] = "communication_since"
OTEL_AGENTS_QUERY_PARAM_CLIENT_VERSION: Final[str] = "client_version"
OTEL_AGENTS_QUERY_PARAM_MDISCONNECTED: Final[str] = "mdisconnected"
OTEL_AGENTS_QUERY_PARAM_SUPPORTS_COMMAND_NAME: Final[str] = "supports_command_name"
OTEL_AGENTS_QUERY_PARAM_SERVICE_INSTANCE_ID: Final[str] = "service_instance_id"
OTEL_AGENTS_QUERY_PARAM_HOST_NAME: Final[str] = "host_name"
OTEL_AGENTS_QUERY_PARAM_HOST_IP: Final[str] = "host_ip"
OTEL_AGENTS_QUERY_PARAM_INVERT_FILTER: Final[str] = "invertFilter"

OTEL_AGENT_SCHEMA_PROPERTIES: Final[dict[str, Any]] = {
    "client_id": {
        "type": "string",
        "description": (
            "Unique client identifier (typically hex-encoded instance UID; "
            "may be \"unknown\" for incomplete identity)."
        ),
    },
    "capabilities": {
        "type": "array",
        "description": (
            "Decoded OpAMP capability names currently reported by the client."
        ),
        "items": {"type": "string"},
    },
    "custom_capabilities_reported": {
        "type": "array",
        "description": "Custom capability FQDN values reported by the client.",
        "items": {"type": "string"},
    },
    "agent_description": {
        "type": "string",
        "nullable": True,
        "description": "Text representation of the latest AgentDescription payload.",
    },
    "node_age_seconds": {
        "type": "number",
        "format": "double",
        "nullable": True,
        "description": "Elapsed seconds since the provider first observed this client.",
    },
    "last_communication": {
        "type": "string",
        "format": "date-time",
        "nullable": True,
        "description": "Timestamp of the most recent AgentToServer message.",
    },
    "last_channel": {
        "type": "string",
        "enum": ["HTTP", "websocket"],
        "nullable": True,
        "description": "Transport channel used by the most recent communication.",
    },
    "remote_addr": {
        "type": "string",
        "nullable": True,
        "description": "Last known source IP address for this client.",
    },
    "current_config": {
        "type": "string",
        "nullable": True,
        "description": "Latest effective/current config reported by the client.",
    },
    "current_config_version": {
        "type": "string",
        "nullable": True,
        "description": "Version identifier for current_config.",
    },
    "requested_config": {
        "type": "string",
        "nullable": True,
        "description": "Most recently requested config payload queued by the provider.",
    },
    "requested_config_version": {
        "type": "string",
        "nullable": True,
        "description": "Version identifier attached to requested_config.",
    },
    "requested_config_apply_at": {
        "type": "string",
        "format": "date-time",
        "nullable": True,
        "description": (
            "Optional timestamp indicating when requested_config should be applied."
        ),
    },
    "client_version": {
        "type": "string",
        "nullable": True,
        "description": (
            "Client software version extracted from service.version in "
            "agent description."
        ),
    },
    "features": {
        "type": "array",
        "description": "Feature flags tracked outside OpAMP capability bits.",
        "items": {"type": "string"},
    },
    "commands": {
        "type": "array",
        "description": (
            "Queued command records for this client, including sent/unsent state."
        ),
        "items": {"$ref": "#/components/schemas/CommandRecord"},
    },
    "events": {
        "type": "array",
        "description": (
            "Recent event timeline entries; items are generic events or command events."
        ),
        "items": {
            "anyOf": [
                {"$ref": "#/components/schemas/EventHistory"},
                {"$ref": "#/components/schemas/CommandRecord"},
            ]
        },
    },
    "next_actions": {
        "type": "array",
        "nullable": True,
        "description": (
            "Ordered list of server next-actions to apply on upcoming client check-ins."
        ),
        "items": {"type": "string"},
    },
    "next_expected_communication": {
        "type": "string",
        "format": "date-time",
        "nullable": True,
        "description": (
            "Predicted next communication timestamp based on heartbeat behavior."
        ),
    },
    "heartbeat_frequency": {
        "type": "integer",
        "minimum": 1,
        "description": "Expected heartbeat frequency in seconds for this client.",
    },
    "first_seen": {
        "type": "string",
        "format": "date-time",
        "description": "Timestamp when this client record was first created in the store.",
    },
    "component_health": {
        "type": "object",
        "nullable": True,
        "description": "Latest flattened component health map keyed by component name.",
        "additionalProperties": {"$ref": "#/components/schemas/ComponentHealthStatus"},
    },
    "health": {
        "nullable": True,
        "description": (
            "Latest top-level health payload including component health map."
        ),
        "allOf": [{"$ref": "#/components/schemas/HealthPayload"}],
    },
    "disconnected": {
        "type": "boolean",
        "description": "Whether the client has sent an agent_disconnect notification.",
    },
    "disconnected_at": {
        "type": "string",
        "format": "date-time",
        "nullable": True,
        "description": "Timestamp when the client was marked disconnected.",
    },
    "pending_agent_identification": {
        "type": "string",
        "nullable": True,
        "description": (
            "Queued replacement instance UID encoded as hex; "
            "null when no pending replacement."
        ),
    },
    "auth_mechanism": {
        "type": "string",
        "enum": ["mtls", "jwt"],
        "nullable": True,
        "description": (
            "Configured client auth mechanism used when agent authentication "
            "checks are enabled."
        ),
    },
    "message_id": {
        "type": "integer",
        "format": "int64",
        "description": (
            "Last received AgentToServer sequence number; minimum-int sentinel "
            "before first message."
        ),
    },
}

OTEL_AGENT_EXPORT_FIELDS: Final[tuple[str, ...]] = tuple(
    OTEL_AGENT_SCHEMA_PROPERTIES.keys()
)

OTEL_AGENT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "description": "Provider-side snapshot of one OpAMP client record.",
    "properties": deepcopy(OTEL_AGENT_SCHEMA_PROPERTIES),
    "required": list(OTEL_AGENT_EXPORT_FIELDS),
}

OTEL_AGENTS_RESPONSE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "description": "Connected OpAMP agents currently tracked by the provider.",
    "properties": {
        "agents": {
            "type": "array",
            "description": "Client records for agents not marked as disconnected.",
            "items": {"$ref": OTEL_AGENT_SCHEMA_REF},
        },
        "total": {
            "type": "integer",
            "minimum": 0,
            "description": "Count of items in the agents array.",
        },
    },
    "required": ["agents", "total"],
}

OTEL_AGENTS_QUERY_PARAMETERS: Final[list[dict[str, Any]]] = [
    {
        "name": OTEL_AGENTS_QUERY_PARAM_AGENT_DESCRIPTION,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": (
            "Case-insensitive substring filter against `agent_description`."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_CLIENT_ID,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": "Case-insensitive substring filter against `client_id`.",
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_BEFORE,
        "in": "query",
        "required": False,
        "schema": {"type": "string", "format": "date-time"},
        "description": (
            "Return only agents where `last_communication` is strictly less than "
            "this timestamp."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_COMMUNICATION_SINCE,
        "in": "query",
        "required": False,
        "schema": {"type": "string", "format": "date-time"},
        "description": (
            "Return only agents where `last_communication` is strictly greater than "
            "this timestamp."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_CLIENT_VERSION,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": "Case-insensitive substring filter against `client_version`.",
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_MDISCONNECTED,
        "in": "query",
        "required": False,
        "schema": {"type": "boolean"},
        "description": (
            "When omitted, only connected agents are returned. "
            "When set, filters by the `disconnected` field."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_SUPPORTS_COMMAND_NAME,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": (
            "Case-insensitive command-name filter against command metadata "
            "(operation, display name, or capability fqdn) and client-reported "
            "command support."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_SERVICE_INSTANCE_ID,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": (
            "Case-insensitive substring filter against `service.instance.id` values "
            "extracted from `agent_description` (falls back to `client_id` when "
            "service instance id is unavailable)."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_HOST_NAME,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": (
            "Case-insensitive substring filter against `host.name` extracted from "
            "`agent_description`."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_HOST_IP,
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": (
            "Case-insensitive substring filter against host IP values extracted "
            "from `remote_addr` and `host.ip` attributes."
        ),
    },
    {
        "name": OTEL_AGENTS_QUERY_PARAM_INVERT_FILTER,
        "in": "query",
        "required": False,
        "schema": {"type": "boolean"},
        "description": (
            "When true, invert all active text/host/command/disconnected/time "
            "filters and return non-matching records."
        ),
    },
]


def apply_otel_agents_openapi_contract(spec: dict[str, Any]) -> dict[str, Any]:
    """Inject shared otel agent schemas into an OpenAPI document."""
    components = spec.setdefault("components", {})
    if not isinstance(components, dict):
        return spec
    schemas = components.setdefault("schemas", {})
    if not isinstance(schemas, dict):
        return spec

    schemas[OTEL_AGENT_SCHEMA_NAME] = deepcopy(OTEL_AGENT_SCHEMA)
    schemas[OTEL_AGENTS_RESPONSE_SCHEMA_NAME] = deepcopy(OTEL_AGENTS_RESPONSE_SCHEMA)

    paths = spec.get("paths")
    if isinstance(paths, dict):
        otel_agents_path = paths.get("/tool/otelAgents")
        if isinstance(otel_agents_path, dict):
            get_operation = otel_agents_path.get("get")
            if isinstance(get_operation, dict):
                # Dependency note:
                # query-parameter docs are externalized here so clients can inspect one
                # stable source of filter semantics even when handler internals evolve.
                get_operation["parameters"] = deepcopy(OTEL_AGENTS_QUERY_PARAMETERS)
                responses = get_operation.get("responses")
                if isinstance(responses, dict):
                    ok_response = responses.get("200")
                    if isinstance(ok_response, dict):
                        content = ok_response.get("content")
                        if isinstance(content, dict):
                            app_json = content.get("application/json")
                            if isinstance(app_json, dict):
                                app_json["schema"] = {
                                    "$ref": OTEL_AGENTS_RESPONSE_SCHEMA_REF
                                }
    return spec
