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

"""Discovery utilities for custom handler implementations."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import pathlib
import types
import uuid
from typing import TYPE_CHECKING

from opamp_consumer.custom_handlers.handler_interface import (
    CustomMessageHandlerInterface,
)

if TYPE_CHECKING:
    from opamp_consumer.abstract_client import OpAMPClientData


def _load_module_from_path(path: pathlib.Path) -> types.ModuleType | None:
    """Dynamically import a handler module from disk and return it when load succeeds.

    Args:
        path: Filesystem path to a Python module file.

    Returns:
        Imported module object, or None when module loading fails.
    """
    module_name = f"opamp_custom_{path.stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _discover_handler_classes(
    folder: pathlib.Path,
) -> list[type[CustomMessageHandlerInterface]]:
    """Discover concrete custom-handler classes from Python modules in a folder.

    Args:
        folder: Directory containing candidate handler Python files.

    Returns:
        List of handler class types discovered under the folder.
    """
    classes: list[type[CustomMessageHandlerInterface]] = []
    for path in folder.glob("*.py"):
        if path.name.startswith("__"):
            continue
        module = _load_module_from_path(path)
        if module is None:
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, CustomMessageHandlerInterface):
                continue
            if obj is CustomMessageHandlerInterface:
                continue
            classes.append(obj)
    return classes


def discover_handlers(
    folder: str | pathlib.Path,
    client_data: OpAMPClientData | None = None,
    allow_custom_capabilities: bool = False,
) -> dict[str, str]:
    """Return a map of fqdn -> class name for handlers in a folder."""
    registry: dict[str, str] = {}
    for fqdn, cls in build_factory_lookup(
        folder,
        client_data=client_data,
        allow_custom_capabilities=allow_custom_capabilities,
    ).items():
        registry[fqdn] = cls.__name__
    return registry


def build_factory_lookup(
    folder: str | pathlib.Path,
    client_data: OpAMPClientData | None = None,
    allow_custom_capabilities: bool = False,
) -> dict[str, type[CustomMessageHandlerInterface]]:
    """Build and return the custom message handler factory lookup."""
    logger = logging.getLogger(__name__)
    if not allow_custom_capabilities:
        logger.info(
            "Custom capabilities disabled by config; handler registry discovery skipped"
        )
        return {}
    folder_path = pathlib.Path(folder)
    if not folder_path.exists():
        return {}
    lookup: dict[str, type[CustomMessageHandlerInterface]] = {}
    for cls in _discover_handler_classes(folder_path):
        try:
            instance = cls()
            if client_data is not None:
                instance.set_client_data(client_data)
            lookup[instance.get_reverse_fqdn()] = cls
        except Exception:
            continue
    if lookup:
        logger.info(
            "Custom capabilities available: %s",
            ", ".join(sorted(lookup.keys())),
        )
    else:
        logger.info("Custom capabilities available: none")
    return lookup


def create_handler(
    fqdn: str,
    folder: str | pathlib.Path,
    client_data: OpAMPClientData | None = None,
    factory_lookup: dict[str, type[CustomMessageHandlerInterface]] | None = None,
    allow_custom_capabilities: bool = False,
) -> CustomMessageHandlerInterface | None:
    """Create a handler instance by fqdn from a folder of handlers."""
    lookup = factory_lookup or build_factory_lookup(
        folder,
        client_data=client_data,
        allow_custom_capabilities=allow_custom_capabilities,
    )
    cls = lookup.get(fqdn)
    if cls is None:
        return None
    try:
        instance = cls()
        if client_data is not None:
            instance.set_client_data(client_data)
        return instance
    except Exception as err:
        logging.getLogger(__name__).error(
            "Error with custom handlers - create handler - %s", err
        )
        return None
    return None
