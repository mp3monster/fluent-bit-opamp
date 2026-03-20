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

"""Command object interfaces and factory implementations."""

from __future__ import annotations

from opamp_provider.chatop_command import ChatOpCommand
from opamp_provider.command_interface import CommandObjectInterface
from opamp_provider.command_restart_agent import RestartAgent


def command_object_factory(
    *,
    classifier: str,
    operation: str,
    key_values: dict[str, str] | None = None,
) -> CommandObjectInterface:
    """Create a command object from classifier and operation."""
    normalized_classifier = classifier.strip().lower()
    normalized_operation = operation.strip().lower()

    if normalized_classifier == "command" and normalized_operation == "restart":
        command_obj = RestartAgent(key_values=key_values)
        return command_obj
    if normalized_classifier == "custom" and normalized_operation == "chatopcommand":
        command_obj = ChatOpCommand(key_values=key_values)
        return command_obj

    raise ValueError(
        f"Unsupported command object classifier={normalized_classifier} operation={normalized_operation}"
    )


__all__ = [
    "CommandObjectInterface",
    "RestartAgent",
    "ChatOpCommand",
    "command_object_factory",
]
