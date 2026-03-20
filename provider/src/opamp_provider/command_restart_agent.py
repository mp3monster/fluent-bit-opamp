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

"""Restart command object implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from opamp_provider.command_interface import CommandObjectInterface


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class RestartAgent(CommandObjectInterface):
    """Concrete command object for a restart operation."""

    def __init__(
        self,
        *,
        command_time: datetime | None = None,
        key_values: dict[str, str] | None = None,
    ) -> None:
        self._command_time = command_time or _utc_now()
        self._key_values = key_values or {}

    def get_command_classifier(self) -> str:
        return "command"

    def get_command_type(self) -> str:
        return "restart"

    def get_command_time(self) -> datetime:
        return self._command_time

    def get_command_description(self) -> str:
        return "Restart Agent"

    def set_key_value_dictionary(self, key_values: dict[str, str]) -> None:
        self._key_values = dict(key_values)

    def get_key_value_dictionary(self) -> dict[str, str]:
        return dict(self._key_values)

    def get_capability_fqdn(self) -> str | None:
        # This uses the shared command framework for a default OpAMP feature (restart),
        # so it should not appear in the list of available custom commands.
        return None
