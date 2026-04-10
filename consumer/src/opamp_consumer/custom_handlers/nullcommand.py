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

"""Custom handler for provider nullcommand messages."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from opamp_consumer.custom_handlers.handler_interface import (
    CustomMessageHandlerInterface,
)
from opamp_consumer.proto import opamp_pb2

if TYPE_CHECKING:
    from opamp_consumer.abstract_client import OpAMPClientData
    from opamp_consumer.opamp_client_interface import OpAMPClientInterface

NULLCOMMAND_CAPABILITY = (
    "org.mp3monster.opamp_provider.nullcommand"
)  # Capability routed to null-command handler.
NULLCOMMAND_DUMMY_VALUE = "dummyValue"  # Custom payload key logged by this handler.


class NullCommand(CustomMessageHandlerInterface):
    """Handle nullcommand custom messages by logging the dummy payload string."""

    def __init__(self) -> None:
        """Initialize runtime fields used to process nullcommand payloads."""
        super().__init__()
        self._data: OpAMPClientData | None = None
        self._dummy_value: str = ""

    def set_client_data(self, data: OpAMPClientData) -> None:
        """Attach client runtime data for handler execution."""
        self._data = data
        logging.getLogger(__name__).info("NullCommand.set_client_data called")

    def get_fqdn(self) -> str:
        """Return the capability FQDN that routes messages to this handler."""
        return NULLCOMMAND_CAPABILITY

    def handle_message(self, message: str, message_type: str) -> None:
        """Parse and cache `dummyValue` from inbound custom message JSON."""
        self._dummy_value = ""
        if message:
            try:
                payload = json.loads(message)
                if isinstance(payload, dict):
                    self._dummy_value = str(
                        payload.get(NULLCOMMAND_DUMMY_VALUE, "") or ""
                    )
            except json.JSONDecodeError:
                self._dummy_value = ""
        logging.getLogger(__name__).info(
            "NullCommand.handle_message called message_type=%s",
            message_type,
        )

    def execute_action(
        self, action: str, opamp_client: OpAMPClientInterface
    ) -> opamp_pb2.CustomMessage | None:
        """Log `dummyValue` and perform no further action."""
        logging.getLogger(__name__).info(
            "NullCommand.execute_action called action=%s dummyValue=%s",
            action or "nullcommand",
            self._dummy_value,
        )
        return None
