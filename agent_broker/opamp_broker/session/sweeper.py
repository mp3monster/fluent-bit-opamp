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

"""Background sweeper that expires idle conversation sessions.

The sweeper runs periodically to enforce memory hygiene and prompt users when
context has been cleared after inactivity.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from opamp_broker.session.manager import SessionManager

logger = logging.getLogger(__name__)


class SessionSweeper:
    """Periodic idle-session expiration worker for the broker runtime."""

    def __init__(
        self,
        session_manager: SessionManager,
        idle_timeout_seconds: int,
        interval_seconds: int,
        on_expire: Callable[[str, str, str], Awaitable[None]],
    ) -> None:
        """Configure sweeper cadence and expiration callback behavior.

        Why this approach:
        injecting ``on_expire`` decouples traversal logic from side effects like
        Slack messaging, making expiration behavior easier to test.

        Args:
            session_manager: Session storage used to enumerate conversations.
            idle_timeout_seconds: Max idle age before a session is expired.
            interval_seconds: Delay between sweep passes.
            on_expire: Async callback receiving channel, thread, and session key.

        Returns:
            None: Stores configuration and initializes shutdown signaling.
        """
        self.session_manager = session_manager
        self.idle_timeout_seconds = idle_timeout_seconds
        self.interval_seconds = interval_seconds
        self.on_expire = on_expire
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        """Continuously expire sessions that exceed the idle timeout.

        Why this loop:
        periodic polling with a shutdown event is simple, predictable, and works
        without requiring per-session timers.

        Returns:
            None: Runs until ``stop`` is called.
        """
        while not self._shutdown.is_set():
            now = time.time()
            sessions = await self.session_manager.all_sessions()
            for session in sessions:
                if now - session.last_activity_at > self.idle_timeout_seconds:
                    logger.info(
                        "expiring idle session",
                        extra={
                            "event": "session.expire",
                            "context": {"session_key": session.key},
                        },
                    )
                    await self.on_expire(
                        session.channel_id,
                        session.thread_ts,
                        session.key,
                    )
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=self.interval_seconds
                )
            except TimeoutError:
                continue

    def stop(self) -> None:
        """Request graceful termination of the sweeper loop.

        Returns:
            None: Sets the internal shutdown event.
        """
        self._shutdown.set()
