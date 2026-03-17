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
import pathlib
import types
import uuid

from opamp_consumer.client import OpAMPClientData
from opamp_consumer.custom_handlers.interface import CustomMessageHandlerInterface


def _load_module_from_path(path: pathlib.Path) -> types.ModuleType | None:
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


def _discover_handler_classes(folder: pathlib.Path) -> list[type[CustomMessageHandlerInterface]]:
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
) -> dict[str, str]:
    """Return a map of fqdn -> class name for handlers in a folder."""
    folder_path = pathlib.Path(folder)
    if not folder_path.exists():
        return {}
    registry: dict[str, str] = {}
    for cls in _discover_handler_classes(folder_path):
        try:
            instance = cls()
            if client_data is not None:
                instance.set_client_data(client_data)
            registry[instance.get_fqdn()] = cls.__name__
        except Exception:
            continue
    return registry


def create_handler(
    fqdn: str,
    folder: str | pathlib.Path,
    client_data: OpAMPClientData | None = None,
) -> CustomMessageHandlerInterface | None:
    """Create a handler instance by fqdn from a folder of handlers."""
    folder_path = pathlib.Path(folder)
    if not folder_path.exists():
        return None
    for cls in _discover_handler_classes(folder_path):
        try:
            instance = cls()
            if client_data is not None:
                instance.set_client_data(client_data)
            if instance.get_fqdn() == fqdn:
                return instance
        except Exception:
            continue
    return None
