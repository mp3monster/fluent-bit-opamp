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

from opamp_provider.command_interface import CommandObjectInterface
from opamp_provider.command_implementations.command_chatops import ChatOpCommand
from opamp_provider.command_implementations.command_nullcommand import (
    CommandNullCommand,
)
from opamp_provider.command_implementations.command_restart_agent import RestartAgent
from opamp_provider.command_implementations.command_shutdown_agent import (
    CommandShutdownAgent,
)

_IMPLEMENTATIONS_PACKAGE = "opamp_provider.command_implementations"
# Module discovery filter for command implementation files.
_COMMAND_MODULE_SUBSTRING = "command"
# Canonical dictionary keys used for command payload normalization and metadata.
_KEY_ACTION = "action"
_KEY_OPERATION = "operation"
_KEY_CAPABILITY = "capability"
_KEY_FQDN = "fqdn"
_KEY_PARAMETER_NAME = "parametername"
_KEY_DISPLAY_NAME = "displayname"
_KEY_DESCRIPTION = "description"
_KEY_CLASSIFIER = "classifier"
_KEY_SCHEMA = "schema"
# Supported classifier values accepted by command routing/factory logic.
_CLASSIFIER_COMMAND = "command"
_CLASSIFIER_CUSTOM = "custom"
_CLASSIFIER_CUSTOM_COMMAND = "custom_command"
CommandKey = tuple[str, str]
CommandType = type[CommandObjectInterface]
_INTERNAL_SCHEMA_PARAMETERS = {_KEY_CLASSIFIER, "type", "data"}
_LOGGER = logging.getLogger(__name__)


def _load_command_modules() -> list[object]:
    """Import command implementation modules from the implementations package.

    Returns:
        A list of imported module objects containing command classes. Modules
        are filtered to names containing the configured command substring.
    """
    implementations_pkg = importlib.import_module(_IMPLEMENTATIONS_PACKAGE)
    package_paths = getattr(implementations_pkg, "__path__", None)
    if package_paths is None:
        return []
    imported_modules: list[object] = []
    for module_info in pkgutil.iter_modules(package_paths):
        module_name = module_info.name
        if module_name.startswith("_"):
            continue
        if _COMMAND_MODULE_SUBSTRING not in module_name:
            continue
        _LOGGER.debug(
            "loading command module package=%s module=%s",
            _IMPLEMENTATIONS_PACKAGE,
            module_name,
        )
        imported_modules.append(
            importlib.import_module(f"{_IMPLEMENTATIONS_PACKAGE}.{module_name}")
        )
    return imported_modules


def _discover_command_classes() -> dict[CommandKey, CommandType]:
    """Discover concrete command classes that implement `CommandObjectInterface`.

    Returns:
        Mapping keyed by `(classifier, operation)` to concrete command class.

    Raises:
        ValueError: If duplicate `(classifier, operation)` registrations are found.
    """
    discovered: dict[CommandKey, CommandType] = {}
    for module in _load_command_modules():
        for member_name, command_class in inspect.getmembers(module, inspect.isclass):
            _LOGGER.debug(
                "inspecting command member name=%s class=%s",
                member_name,
                command_class.__name__,
            )
            if not issubclass(command_class, CommandObjectInterface):
                continue
            if command_class is CommandObjectInterface or inspect.isabstract(
                command_class
            ):
                continue
            command_instance = command_class()
            key_values = command_instance.get_key_value_dictionary()
            operation = str(key_values.get(_KEY_ACTION, "")).strip().lower()
            if not operation:
                continue
            key = (
                command_instance.get_command_classifier().strip().lower(),
                operation,
            )
            if key in discovered:
                _LOGGER.error(
                    "duplicate command registration classifier=%s operation=%s existing=%s duplicate=%s",
                    key[0],
                    key[1],
                    discovered[key].__name__,
                    command_class.__name__,
                )
                raise ValueError(
                    "Duplicate command registration for classifier=%s operation=%s"
                    % (key[0], key[1])
                )
            discovered[key] = command_class
            _LOGGER.debug(
                "registered command class=%s classifier=%s operation=%s module=%s",
                command_class.__name__,
                key[0],
                key[1],
                command_class.__module__,
            )
    return discovered


_COMMAND_REGISTRY: dict[CommandKey, CommandType] = _discover_command_classes()


def _get_command_registry_by_standard_filter(
    *,
    parameter_exclude_opamp_standard: bool,
) -> dict[CommandKey, CommandType]:
    """Filter command registry by OpAMP-standard classification.

    Args:
        parameter_exclude_opamp_standard: When True, include only non-standard
            custom commands; when False, include only OpAMP-standard commands.

    Returns:
        Filtered `(classifier, operation) -> command class` mapping.
    """
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
        param_name = str(row.get(_KEY_PARAMETER_NAME, "")).strip().lower()
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


# Design intent: custom commands should be "drop-in" via discovery.
# These maps are derived once from the registry so adding a new custom command
# implementation does not require editing factory conditionals.
_CUSTOM_COMMAND_CLASS_BY_OPERATION: dict[str, CommandType] = {}
_CUSTOM_COMMAND_CLASS_BY_CAPABILITY: dict[str, CommandType] = {}
for key, command_class in _COMMAND_REGISTRY.items():
    classifier, operation = key
    if classifier != _CLASSIFIER_CUSTOM:
        continue
    normalized_operation = str(operation).strip().lower()
    if normalized_operation:
        existing = _CUSTOM_COMMAND_CLASS_BY_OPERATION.get(normalized_operation)
        if existing is not None and existing is not command_class:
            raise ValueError(
                "Duplicate custom command operation mapping for operation=%s" % normalized_operation
            )
        _CUSTOM_COMMAND_CLASS_BY_OPERATION[normalized_operation] = command_class
    capability_fqdn = str(_COMMAND_FQDN_MAP.get(key, "")).strip()
    if capability_fqdn:
        existing = _CUSTOM_COMMAND_CLASS_BY_CAPABILITY.get(capability_fqdn)
        if existing is not None and existing is not command_class:
            raise ValueError(
                "Duplicate custom capability mapping for capability=%s" % capability_fqdn
            )
        _CUSTOM_COMMAND_CLASS_BY_CAPABILITY[capability_fqdn] = command_class


def _new_command_object(
    command_class: CommandType,
    *,
    values: dict[str, str],
) -> CommandObjectInterface:
    """Instantiate and initialize a command object with provided key/value pairs."""
    instance = command_class()
    instance.set_key_value_dictionary(values)
    return instance


def _resolve_custom_command_class(
    *,
    capability: str,
    operation: str,
    action: str,
) -> CommandType | None:
    """Resolve custom command class by capability first, then operation/action."""
    # Design intent: prefer capability when present because it is globally unique
    # and survives operation renames; operation/action are compatibility fallbacks.
    if capability:
        by_capability = _CUSTOM_COMMAND_CLASS_BY_CAPABILITY.get(capability)
        if by_capability is not None:
            return by_capability
    if operation:
        by_operation = _CUSTOM_COMMAND_CLASS_BY_OPERATION.get(operation)
        if by_operation is not None:
            return by_operation
    if action:
        return _CUSTOM_COMMAND_CLASS_BY_OPERATION.get(action)
    return None


def get_registered_command_keys(
    parameter_exclude_opamp_standard: bool = True,
    includedisplayname: bool = True,
) -> tuple[CommandKey, ...] | dict[str, str]:
    """Return command registration results in key or display-map form.

    Args:
        parameter_exclude_opamp_standard: Filter mode for OpAMP-standard commands.
        includedisplayname: When True, return `fqdn -> displayname`; otherwise
            return sorted `(classifier, operation)` tuples.

    Returns:
        Either a tuple of command keys or a display map for custom capabilities.
    """
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
    """Return discovered non-OpAMP-standard command keys or display map.

    Args:
        includedisplayname: Whether to return display map rather than key tuples.

    Returns:
        Non-standard command registrations in requested output shape.
    """
    return get_registered_command_keys(
        parameter_exclude_opamp_standard=True,
        includedisplayname=includedisplayname,
    )


def get_registered_command_fqdns() -> dict[CommandKey, str]:
    """Return discovered command reverse-FQDN capability mappings.

    Returns:
        Mapping from `(classifier, operation)` to capability reverse-FQDN.
    """
    return dict(_COMMAND_FQDN_MAP)


def get_custom_capabilities_list() -> tuple[str, ...]:
    """Return unique custom capability FQDNs discovered at startup.

    Returns:
        Sorted tuple of unique custom command capability names.
    """
    return tuple(sorted(set(_COMMAND_FQDN_MAP.values())))


def get_command_fqdn(*, classifier: str, operation: str) -> str:
    """Return reverse-FQDN for a classifier/operation pair.

    Args:
        classifier: Command classifier (for example `custom`).
        operation: Command operation/action key.

    Returns:
        Capability reverse-FQDN if known, else an empty string.
    """
    key = (classifier.strip().lower(), operation.strip().lower())
    return _COMMAND_FQDN_MAP.get(key, "")


def command_object_factory(
    *,
    classifier: str,
    key_values: dict[str, str] | None = None,
) -> CommandObjectInterface:
    """Create a concrete command object from classifier and routing fields.

    Args:
        classifier: Requested classifier (for example `command` or `custom`).
        key_values: Raw key/value command payload, including operation and
            optional capability metadata.

    Returns:
        Concrete command object implementing `CommandObjectInterface`.

    Raises:
        ValueError: If the classifier/operation/capability mapping is unsupported.
    """
    normalized_classifier = classifier.strip().lower()
    values = dict(key_values or {})
    operation = str(values.get(_KEY_OPERATION, "")).strip().lower()
    action = str(values.get(_KEY_ACTION, "")).strip().lower()
    capability = str(values.get(_KEY_CAPABILITY, "") or values.get(_KEY_FQDN, "")).strip()
    _LOGGER.debug(
        "command_object_factory input classifier=%s operation=%s action=%s capability=%s",
        normalized_classifier,
        operation,
        action,
        capability,
    )

    if normalized_classifier == _CLASSIFIER_COMMAND:
        _LOGGER.debug("command_object_factory selected class=%s", RestartAgent.__name__)
        return _new_command_object(RestartAgent, values=values)

    if normalized_classifier in {_CLASSIFIER_CUSTOM, _CLASSIFIER_CUSTOM_COMMAND}:
        command_class = _resolve_custom_command_class(
            capability=capability,
            operation=operation,
            action=action,
        )
        if command_class is not None:
            _LOGGER.debug(
                "command_object_factory selected class=%s",
                command_class.__name__,
            )
            return _new_command_object(command_class, values=values)
        _LOGGER.error(
            "unsupported command object mapping classifier=%s operation=%s capability=%s action=%s",
            normalized_classifier,
            operation,
            capability,
            action,
        )
        raise ValueError(
            "Unsupported command object classifier=%s operation=%s capability=%s action=%s"
            % (normalized_classifier, operation, capability, action)
        )

    _LOGGER.error(
        "unsupported command object classifier=%s", normalized_classifier
    )
    raise ValueError(
        "Unsupported command object classifier=%s" % normalized_classifier
    )


def get_command_metadata(
    *,
    parameter_exclude_opamp_standard: bool = True,
    custom_only: bool = False,
) -> list[dict[str, object]]:
    """Return command metadata records for registry/API consumers.

    Args:
        parameter_exclude_opamp_standard: Filter mode for OpAMP-standard commands.
        custom_only: When True, include only custom command entries.

    Returns:
        Sorted metadata records containing fqdn, display name, description,
        classifier, operation, and user schema.
    """
    metadata: list[dict[str, object]] = []
    filtered_registry = _get_command_registry_by_standard_filter(
        parameter_exclude_opamp_standard=parameter_exclude_opamp_standard
    )
    for (classifier_key, operation_key), command_class in filtered_registry.items():
        instance = command_class()
        classifier = classifier_key
        if custom_only and classifier != _CLASSIFIER_CUSTOM:
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
                _KEY_FQDN: capability_fqdn,
                _KEY_DISPLAY_NAME: instance.getdisplayname(),
                _KEY_DESCRIPTION: instance.get_command_description(),
                _KEY_CLASSIFIER: classifier,
                _KEY_OPERATION: operation_key,
                _KEY_SCHEMA: schema,
            }
        )
    metadata.sort(key=lambda item: str(item.get(_KEY_DISPLAY_NAME, "")).lower())
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
