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

"""Command queue request parsing and validation helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any

from opamp_provider.command_record import CommandRecord
from opamp_provider.commands import command_object_factory
from opamp_provider.state import ClientStore

CLASSIFIER_COMMAND = "command"
CLASSIFIER_CUSTOM_COMMAND = "custom_command"
CLASSIFIER_CUSTOM = "custom"
COMMAND_RESTART = "restart"
COMMAND_FORCE_RESYNC = "forceresync"
LOG_REST_COMMAND = "queued command for client %s classifier=%s action=%s at %s"
_MCP_VALIDATION_MESSAGE_PREFIX = "Custom command request rejected: "
_MCP_RESERVED_PARAMETER_KEYS = {
    "classifier",
    "operation",
    "action",
    "capability",
}


class QueueCommandRequestError(Exception):
    """Structured command-queue request validation error."""

    def __init__(self, payload: dict[str, Any], status_code: HTTPStatus) -> None:
        super().__init__(str(payload.get("error", "invalid command payload")))
        self.payload = payload
        self.status_code = status_code


def _noop_command_builder(_response: Any, _command: CommandRecord) -> Any:
    """No-op builder used only for command-routing-key validation."""
    return _response


def _validate_mcp_parameters(parameters: Any) -> dict[str, str]:
    """Validate and normalize user-provided MCP key/value parameter pairs."""
    if parameters is None:
        return {}
    if not isinstance(parameters, dict):
        raise QueueCommandRequestError(
            {"error": "parameters must be an object/dictionary"},
            HTTPStatus.BAD_REQUEST,
        )
    normalized: dict[str, str] = {}
    for raw_key, raw_value in parameters.items():
        key = str(raw_key).strip()
        if not key:
            raise QueueCommandRequestError(
                {"error": "parameter keys must be non-empty strings"},
                HTTPStatus.BAD_REQUEST,
            )
        if key.lower() in _MCP_RESERVED_PARAMETER_KEYS:
            raise QueueCommandRequestError(
                {
                    "error": (
                        f"parameter key '{key}' is reserved and cannot be overridden"
                    )
                },
                HTTPStatus.BAD_REQUEST,
            )
        if isinstance(raw_value, (dict, list, tuple, set)):
            raise QueueCommandRequestError(
                {
                    "error": (
                        f"parameter '{key}' must be a primitive value "
                        "(string/number/boolean)"
                    )
                },
                HTTPStatus.BAD_REQUEST,
            )
        normalized[key] = str(raw_value)
    return normalized


def queue_command_from_payload(
    *,
    client_id: str,
    payload: Any,
    store: ClientStore,
    max_events: int,
    command_builders: Mapping[
        tuple[str, str], Callable[[Any, CommandRecord], Any]
    ],
    logger: logging.Logger,
) -> CommandRecord:
    """Validate and queue a command payload from `/api/clients/<id>/commands`."""
    logger.debug("queue_command request client_id=%s payload=%s", client_id, payload)
    pairs = None
    if isinstance(payload, list):
        pairs = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("pairs"), list):
            pairs = payload["pairs"]
    if not isinstance(pairs, list) or not pairs:
        raise QueueCommandRequestError(
            {"error": "pairs array is required"},
            HTTPStatus.BAD_REQUEST,
        )
    logger.debug("queue_command parsed pairs client_id=%s pairs=%s", client_id, pairs)

    normalized_pairs: list[dict[str, str]] = []
    values: dict[str, str] = {}
    for pair in pairs:
        if not isinstance(pair, dict) or "key" not in pair or "value" not in pair:
            raise QueueCommandRequestError(
                {"error": "each pair must include key and value"},
                HTTPStatus.BAD_REQUEST,
            )
        key = str(pair["key"]).strip()
        value = str(pair["value"]).strip()
        if not key:
            raise QueueCommandRequestError(
                {"error": "pair key cannot be empty"},
                HTTPStatus.BAD_REQUEST,
            )
        normalized_pairs.append({"key": key, "value": value})
        values[key.lower()] = value

    classifier = values.get("classifier", "").strip().lower()
    operation = values.get("operation", "").strip().lower()
    action = values.get("action", "").strip().lower()
    routing_action = operation or action
    logger.debug(
        "queue_command routing fields client_id=%s classifier=%s operation=%s action=%s routing_action=%s",
        client_id,
        classifier,
        operation,
        action,
        routing_action,
    )

    if classifier not in {
        CLASSIFIER_COMMAND,
        CLASSIFIER_CUSTOM_COMMAND,
        CLASSIFIER_CUSTOM,
    }:
        raise QueueCommandRequestError(
            {
                "error": "classifier must be command, custom, or custom_command",
                "classifier": classifier,
            },
            HTTPStatus.BAD_REQUEST,
        )
    if not routing_action:
        raise QueueCommandRequestError(
            {"error": "operation is required"},
            HTTPStatus.BAD_REQUEST,
        )

    if (classifier, routing_action) not in command_builders and (
        classifier,
        "*",
    ) not in command_builders:
        logger.debug(
            "queue_command unsupported mapping client_id=%s classifier=%s routing_action=%s builders=%s",
            client_id,
            classifier,
            routing_action,
            sorted(command_builders.keys()),
        )
        raise QueueCommandRequestError(
            {
                "error": "unsupported classifier/action",
                "classifier": classifier,
                "action": routing_action,
            },
            HTTPStatus.BAD_REQUEST,
        )

    # Build a command object when a concrete class exists for the operation.
    key_value_dict = {pair["key"]: pair["value"] for pair in normalized_pairs}
    event_description = f"{classifier} {routing_action} command queued"
    if classifier == CLASSIFIER_COMMAND and routing_action == COMMAND_FORCE_RESYNC:
        event_description = "Force Resync"

    command_obj = None
    if classifier == CLASSIFIER_COMMAND and routing_action == COMMAND_RESTART:
        logger.debug(
            "queue_command building command object client_id=%s classifier=%s routing_action=%s key_values=%s",
            client_id,
            classifier,
            routing_action,
            key_value_dict,
        )
        command_obj = command_object_factory(
            classifier=classifier,
            key_values=key_value_dict,
        )
        command_obj.set_key_value_dictionary(key_value_dict)
        classifier = command_obj.get_command_classifier()
        routing_action = str(routing_action).strip().lower()
        event_description = command_obj.get_command_description()
        logger.debug(
            "queue_command built command object client_id=%s object_type=%s classifier=%s routing_action=%s",
            client_id,
            command_obj.__class__.__name__,
            classifier,
            routing_action,
        )
    elif classifier == CLASSIFIER_CUSTOM:
        # Design intent: keep wildcard routing for extensibility, but still reject
        # unknown custom operations early so typos do not queue opaque payloads.
        logger.debug(
            "queue_command validating custom command object client_id=%s classifier=%s routing_action=%s key_values=%s",
            client_id,
            classifier,
            routing_action,
            key_value_dict,
        )
        try:
            command_obj = command_object_factory(
                classifier=classifier,
                key_values=key_value_dict,
            )
        except ValueError:
            logger.debug(
                "queue_command rejected unknown custom command mapping client_id=%s classifier=%s routing_action=%s",
                client_id,
                classifier,
                routing_action,
            )
            raise QueueCommandRequestError(
                {
                    "error": "unsupported custom command mapping",
                    "classifier": classifier,
                    "action": routing_action,
                },
                HTTPStatus.BAD_REQUEST,
            ) from None

        command_obj.set_key_value_dictionary(key_value_dict)
        classifier = command_obj.get_command_classifier().strip().lower()
        normalized_command_values = command_obj.get_key_value_dictionary()
        routing_action = str(
            normalized_command_values.get("action", routing_action) or routing_action
        ).strip().lower()
        event_description = command_obj.get_command_description()
        logger.debug(
            "queue_command validated custom command object client_id=%s object_type=%s classifier=%s routing_action=%s",
            client_id,
            command_obj.__class__.__name__,
            classifier,
            routing_action,
        )

    cmd = store.queue_command(
        client_id,
        classifier=classifier,
        action=routing_action,
        key_value_pairs=(
            [
                {"key": key_name, "value": key_value}
                for key_name, key_value in command_obj.get_key_value_dictionary().items()
            ]
            if command_obj is not None
            else normalized_pairs
        ),
        event_description=event_description,
        max_events=max_events,
    )
    logger.info(
        LOG_REST_COMMAND,
        client_id,
        cmd.classifier,
        cmd.action,
        cmd.received_at,
    )
    return cmd


def queue_custom_command_from_mcp(
    *,
    client_id: str,
    operation: str,
    capability: str | None,
    parameters: Any,
    store: ClientStore,
    max_events: int,
    logger: logging.Logger,
) -> CommandRecord:
    """Queue one custom command from an MCP tool request with strict validation."""
    normalized_client_id = str(client_id or "").strip()
    if not normalized_client_id:
        raise QueueCommandRequestError(
            {"error": "client_id is required"},
            HTTPStatus.BAD_REQUEST,
        )
    normalized_operation = str(operation or "").strip().lower()
    if not normalized_operation:
        raise QueueCommandRequestError(
            {"error": "operation is required"},
            HTTPStatus.BAD_REQUEST,
        )
    normalized_capability = str(capability or "").strip()
    parameter_values = _validate_mcp_parameters(parameters)

    pairs: list[dict[str, str]] = [
        {"key": "classifier", "value": CLASSIFIER_CUSTOM},
        {"key": "operation", "value": normalized_operation},
    ]
    if normalized_capability:
        pairs.append({"key": "capability", "value": normalized_capability})
    for key, value in parameter_values.items():
        pairs.append({"key": key, "value": value})

    validation_only_builders: dict[tuple[str, str], Callable[[Any, Any], Any]] = {
        (CLASSIFIER_CUSTOM, "*"): _noop_command_builder,
        (CLASSIFIER_CUSTOM_COMMAND, "*"): _noop_command_builder,
    }

    return queue_command_from_payload(
        client_id=normalized_client_id,
        payload={"pairs": pairs},
        store=store,
        max_events=max_events,
        command_builders=validation_only_builders,
        logger=logger,
    )


def build_custom_command_mcp_error_payload(error: QueueCommandRequestError) -> dict[str, Any]:
    """Create a user-friendly MCP tool error payload from validation failures."""
    detail = str(error.payload.get("error", "invalid custom command request")).strip()
    message = _MCP_VALIDATION_MESSAGE_PREFIX + (
        detail if detail else "invalid custom command request"
    )
    return {
        "status": "error",
        "error": message,
        "validation_error": error.payload,
        "status_code": int(error.status_code),
    }
