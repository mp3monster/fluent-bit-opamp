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

"""Interface for custom OpAMP message handling."""

from __future__ import annotations

from abc import ABC, abstractmethod

from opamp_consumer.client import OpAMPClientData


class CustomMessageHandlerInterface(ABC):
    """Defines the contract for custom message handlers."""

    @abstractmethod
    def set_client_data(self, data: OpAMPClientData) -> None:
        """Provide the handler with OpAMP client data."""

    @abstractmethod
    def get_fqdn(self) -> str:
        """Return the fully-qualified domain name for this handler."""

    @abstractmethod
    def handle_message(self, message: str, message_type: str) -> None:
        """Handle an inbound message and type string."""

    @abstractmethod
    def execute_action(self, action: str) -> None:
        """Execute a named action."""
