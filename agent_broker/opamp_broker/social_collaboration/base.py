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

"""Abstract interface for broker social collaboration integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from opamp_broker.session.manager import SessionManager


class SocialCollaborationAdapter(ABC):
    """Contract for chat platform integrations used by the broker runtime."""

    @abstractmethod
    def register_handlers(
        self,
        session_manager: SessionManager,
        compiled_graph: Any,
        config: dict[str, Any],
    ) -> None:
        """Register inbound platform handlers that route messages into the graph."""

    @abstractmethod
    async def start(self) -> None:
        """Start platform event delivery loop and run until cancelled/stopped."""

    @abstractmethod
    async def post_message(self, *, channel_id: str, thread_ts: str, text: str) -> None:
        """Send a platform message to an existing conversation/thread context."""

    async def verify_connection(self) -> dict[str, Any]:
        """Verify adapter connectivity and return an ``ok`` status payload."""
        return {
            "ok": False,
            "error": "connection verification is not implemented for this adapter",
        }
