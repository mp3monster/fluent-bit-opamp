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
import pkgutil
from pathlib import Path

from opamp_provider.chatop_command import ChatOpCommand
from opamp_provider.command_interface import CommandObjectInterface
from opamp_provider.command_restart_agent import RestartAgent

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
            key = (
                command_instance.get_command_classifier().strip().lower(),
                command_instance.get_command_type().strip().lower(),
            )
            if key in discovered:
                raise ValueError(
                    f"Duplicate command registration for classifier={key[0]} operation={key[1]}"
                )
            discovered[key] = class_obj
    return discovered


_COMMAND_REGISTRY: dict[CommandKey, CommandType] = _discover_command_classes()
_COMMAND_FQDN_MAP: dict[CommandKey, str] = {}
for key, command_class in _COMMAND_REGISTRY.items():
    capability_fqdn = command_class().get_capability_fqdn()
    if capability_fqdn is None:
        continue
    normalized_fqdn = capability_fqdn.strip()
    if normalized_fqdn:
        _COMMAND_FQDN_MAP[key] = normalized_fqdn


def get_registered_command_keys() -> tuple[CommandKey, ...]:
    """Return all discovered command (classifier, operation) keys."""
    return tuple(sorted(_COMMAND_REGISTRY.keys()))


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
    operation: str,
    key_values: dict[str, str] | None = None,
) -> CommandObjectInterface:
    """Create a command object from classifier and operation."""
    key = (classifier.strip().lower(), operation.strip().lower())
    command_class = _COMMAND_REGISTRY.get(key)
    if command_class is not None:
        return command_class(key_values=key_values)

    raise ValueError(
        f"Unsupported command object classifier={key[0]} operation={key[1]}"
    )


__all__ = [
    "CommandObjectInterface",
    "RestartAgent",
    "ChatOpCommand",
    "get_registered_command_keys",
    "get_registered_command_fqdns",
    "get_custom_capabilities_list",
    "get_command_fqdn",
    "command_object_factory",
]
