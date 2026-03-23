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

"""Command object discovery, registry, and factory implementations."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from opamp_provider.chatop_command import ChatOpCommand
from opamp_provider.command_interface import CommandObjectInterface
from opamp_provider.command_nullcommand import CommandNullCommand
from opamp_provider.command_restart_agent import RestartAgent
from opamp_provider.command_shutdown_agent import CommandShutdownAgent

_MODULE_EXCLUSIONS = {
    "__init__",
    "app",
    "command_interface",
    "command_record",
    "commands",
    "config",
    "exceptions",
    "server",
    "state",
    "transport",
}

CommandKey = tuple[str, str]
CommandType = type[CommandObjectInterface]
_INTERNAL_SCHEMA_PARAMETERS = {"classifier", "type", "data"}
_LOGGER = logging.getLogger(__name__)


def _module_name_to_import(module_name: str) -> str:
    package_name = __package__ or "opamp_provider"
    return f"{package_name}.{module_name}"


def _load_command_modules() -> list[object]:
    package_path = Path(__file__).resolve().parent
    imported_modules: list[object] = []
    for module_info in pkgutil.iter_modules([str(package_path)]):
        module_name = module_info.name
        if module_name in _MODULE_EXCLUSIONS or module_name.startswith("_"):
            continue
        if "command" not in module_name:
            continue
        imported_modules.append(importlib.import_module(_module_name_to_import(module_name)))
    return imported_modules


def _discover_command_classes() -> dict[CommandKey, CommandType]:
    discovered: dict[CommandKey, CommandType] = {}
    for module in _load_command_modules():
        for _, class_obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(class_obj, CommandObjectInterface):
                continue
            if class_obj is CommandObjectInterface or inspect.isabstract(class_obj):
                continue
            command_instance = class_obj()
            key_values = command_instance.get_key_value_dictionary()
            operation = str(key_values.get("action", "")).strip().lower()
            if not operation:
                continue
            key = (
                command_instance.get_command_classifier().strip().lower(),
                operation,
            )
            if key in discovered:
                raise ValueError(
                    f"Duplicate command registration for classifier={key[0]} operation={key[1]}"
                )
            discovered[key] = class_obj
    return discovered


_COMMAND_REGISTRY: dict[CommandKey, CommandType] = _discover_command_classes()


def _get_command_registry_by_standard_filter(
    *,
    parameter_exclude_opamp_standard: bool,
) -> dict[CommandKey, CommandType]:
    filtered: dict[CommandKey, CommandType] = {}
    for key, command_class in _COMMAND_REGISTRY.items():
        if parameter_exclude_opamp_standard != command_class().isOpAMPStandard():
            filtered[key] = command_class
    return filtered


def _sanitize_parameter_schema(
    schema_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Remove internal OpAMP transport fields from command schema rows."""
    sanitized: list[dict[str, object]] = []
    for row in schema_rows:
        param_name = str(row.get("parametername", "")).strip().lower()
        if not param_name:
            continue
        if param_name in _INTERNAL_SCHEMA_PARAMETERS:
            continue
        sanitized.append(dict(row))
    return sanitized


_COMMAND_FQDN_MAP: dict[CommandKey, str] = {}
for key, command_class in _get_command_registry_by_standard_filter(
    parameter_exclude_opamp_standard=True
).items():
    capability_fqdn = command_class().get_capability_fqdn()
    if capability_fqdn is None:
        continue
    normalized_fqdn = capability_fqdn.strip()
    if normalized_fqdn:
        _COMMAND_FQDN_MAP[key] = normalized_fqdn


def get_registered_command_keys(
    parameter_exclude_opamp_standard: bool = True,
    includedisplayname: bool = True,
) -> tuple[CommandKey, ...] | dict[str, str]:
    """Return command keys or fqdn->displayname map filtered by OpAMP-standard rule."""
    filtered_registry = _get_command_registry_by_standard_filter(
        parameter_exclude_opamp_standard=parameter_exclude_opamp_standard
    )
    if not includedisplayname:
        return tuple(sorted(filtered_registry.keys()))

    display_map: dict[str, str] = {}
    for command_class in filtered_registry.values():
        instance = command_class()
        capability_fqdn = instance.get_capability_fqdn()
        if capability_fqdn is None:
            continue
        normalized_fqdn = capability_fqdn.strip()
        if not normalized_fqdn:
            continue
        display_map[normalized_fqdn] = instance.getdisplayname()
    return display_map


def get_available_command_keys(
    includedisplayname: bool = True,
) -> tuple[CommandKey, ...] | dict[str, str]:
    """Return discovered non-OpAMP-standard command keys."""
    return get_registered_command_keys(
        parameter_exclude_opamp_standard=True,
        includedisplayname=includedisplayname,
    )


def get_registered_command_fqdns() -> dict[CommandKey, str]:
    """Return discovered command reverse-FQDN capability mappings."""
    return dict(_COMMAND_FQDN_MAP)


def get_custom_capabilities_list() -> tuple[str, ...]:
    """Return unique custom capability FQDNs discovered at startup."""
    return tuple(sorted(set(_COMMAND_FQDN_MAP.values())))


def get_command_fqdn(*, classifier: str, operation: str) -> str:
    """Return a command capability reverse-FQDN, or an empty string."""
    key = (classifier.strip().lower(), operation.strip().lower())
    return _COMMAND_FQDN_MAP.get(key, "")


def command_object_factory(
    *,
    classifier: str,
    key_values: dict[str, str] | None = None,
) -> CommandObjectInterface:
    """Create a command object from classifier and internal routing fields."""
    normalized_classifier = classifier.strip().lower()
    values = dict(key_values or {})
    operation = str(values.get("operation", "")).strip().lower()
    action = str(values.get("action", "")).strip().lower()
    capability = str(values.get("capability", "") or values.get("fqdn", "")).strip()
    _LOGGER.debug(
        "command_object_factory input classifier=%s operation=%s action=%s capability=%s",
        normalized_classifier,
        operation,
        action,
        capability,
    )

    if normalized_classifier == "command":
        _LOGGER.debug("command_object_factory selected class=%s", RestartAgent.__name__)
        return RestartAgent(key_values=values)

    if normalized_classifier in {"custom", "custom_command"}:
        if capability == "org.mp3monster.opamp_provider.chatopcommand":
            _LOGGER.debug("command_object_factory selected class=%s", ChatOpCommand.__name__)
            return ChatOpCommand(key_values=values)
        if capability == "org.mp3monster.opamp_provider.command_shutdown_agent":
            _LOGGER.debug(
                "command_object_factory selected class=%s", CommandShutdownAgent.__name__
            )
            return CommandShutdownAgent(key_values=values)
        if capability == "org.mp3monster.opamp_provider.nullcommand":
            _LOGGER.debug(
                "command_object_factory selected class=%s", CommandNullCommand.__name__
            )
            return CommandNullCommand(key_values=values)
        if operation == "chatopcommand":
            _LOGGER.debug("command_object_factory selected class=%s", ChatOpCommand.__name__)
            return ChatOpCommand(key_values=values)
        if operation == "shutdownagent":
            _LOGGER.debug(
                "command_object_factory selected class=%s", CommandShutdownAgent.__name__
            )
            return CommandShutdownAgent(key_values=values)
        if operation == "nullcommand":
            _LOGGER.debug(
                "command_object_factory selected class=%s", CommandNullCommand.__name__
            )
            return CommandNullCommand(key_values=values)
        raise ValueError(
            "Unsupported command object classifier="
            f"{normalized_classifier} operation={operation} capability={capability} action={action}"
        )

    raise ValueError(f"Unsupported command object classifier={normalized_classifier}")


def get_command_metadata(
    *,
    parameter_exclude_opamp_standard: bool = True,
    custom_only: bool = False,
) -> list[dict[str, object]]:
    """Return command metadata records for registry/API consumers."""
    metadata: list[dict[str, object]] = []
    filtered_registry = _get_command_registry_by_standard_filter(
        parameter_exclude_opamp_standard=parameter_exclude_opamp_standard
    )
    for (classifier_key, operation_key), command_class in filtered_registry.items():
        instance = command_class()
        classifier = classifier_key
        if custom_only and classifier != "custom":
            continue
        capability_fqdn = (instance.get_capability_fqdn() or "").strip()
        if custom_only and not capability_fqdn:
            continue
        schema: list[dict[str, object]] = []
        if hasattr(instance, "get_user_parameter_schema"):
            schema = _sanitize_parameter_schema(
                list(getattr(instance, "get_user_parameter_schema")())
            )
        metadata.append(
            {
                "fqdn": capability_fqdn,
                "displayname": instance.getdisplayname(),
                "description": instance.get_command_description(),
                "classifier": classifier,
                "operation": operation_key,
                "schema": schema,
            }
        )
    metadata.sort(key=lambda item: str(item.get("displayname", "")).lower())
    return metadata


__all__ = [
    "CommandObjectInterface",
    "RestartAgent",
    "ChatOpCommand",
    "CommandNullCommand",
    "get_registered_command_keys",
    "get_available_command_keys",
    "get_registered_command_fqdns",
    "get_custom_capabilities_list",
    "get_command_fqdn",
    "get_command_metadata",
    "command_object_factory",
]
