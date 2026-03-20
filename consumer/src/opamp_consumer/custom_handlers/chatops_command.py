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

"""Default custom handler implementation with logging stubs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opamp_consumer.custom_handlers.handler_interface import CustomMessageHandlerInterface

if TYPE_CHECKING:
    from opamp_consumer.client import OpAMPClientData
    from opamp_consumer.opamp_client_interface import OpAMPClientInterface

CHATOPCOMMAND_CAPABILITY = "org.mp3monster.opamp_provider.chatopcommand"


class ChatOpsCommand(CustomMessageHandlerInterface):
    """Stub ChatOps command handler."""

    def __init__(self) -> None:
        super().__init__()
        self._data: OpAMPClientData | None = None

    def set_client_data(self, data: OpAMPClientData) -> None:
        logging.getLogger(__name__).info("ChatOpsCommand.set_client_data called")
        self._data = data

    def get_fqdn(self) -> str:
        logging.getLogger(__name__).info("ChatOpsCommand.get_fqdn called")
        return CHATOPCOMMAND_CAPABILITY

    def handle_message(self, message: str, message_type: str) -> None:
        logging.getLogger(__name__).info(
            "ChatOpsCommand.handle_message called message_type=%s message=%s",
            message_type,
            message,
        )

    def execute_action(self, action: str, opamp_client: OpAMPClientInterface) -> None:
        logging.getLogger(__name__).info(
            "ChatOpsCommand.execute_action called action=%s opamp_client=%s",
            action,
            opamp_client.__class__.__name__,
        )
