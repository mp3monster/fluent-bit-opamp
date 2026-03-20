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

"""Command object interface contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class CommandObjectInterface(ABC):
    """Interface for command object metadata and payload helpers."""

    @abstractmethod
    def get_command_classifier(self) -> str:
        """Return the command classifier."""

    @abstractmethod
    def get_command_type(self) -> str:
        """Return the command operation/type."""

    @abstractmethod
    def get_command_time(self) -> datetime:
        """Return the command creation timestamp."""

    @abstractmethod
    def get_command_description(self) -> str:
        """Return a human-readable description of the command."""

    @abstractmethod
    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        """Set key/value dictionary used by this command object."""

    @abstractmethod
    def get_key_value_dictionary(self) -> dict[str, str]:
        """Return key/value dictionary attached to this command object."""

    @abstractmethod
    def get_capability_fqdn(self) -> str:
        """Return reverse-FQDN capability string for custom messages (or empty)."""
