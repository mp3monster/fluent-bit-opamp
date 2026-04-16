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

"""Thread-scoped in-memory session store for broker conversations.

A lightweight async lock is used instead of external persistence because the
broker only needs short-lived coordination state between Slack messages.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationSession:
    """Mutable per-thread conversation context persisted in memory.

    Why this structure:
    storing both conversational metadata and pending tool actions enables the
    broker to preserve intent between separate Slack events in the same thread.
    """

    key: str
    team_id: str
    channel_id: str
    thread_ts: str
    user_id: str | None = None
    created_at: float = field(default_factory=lambda: time.time())
    last_activity_at: float = field(default_factory=lambda: time.time())
    current_target: str | None = None
    environment: str | None = None
    intent: str | None = None
    last_summary: str | None = None
    pending_action: dict[str, Any] | None = None
    recent_tool_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "active"


class SessionManager:
    """Concurrency-safe CRUD interface for ``ConversationSession`` objects."""

    def __init__(self) -> None:
        """Initialize an empty session map protected by an async lock.

        Returns:
            None: Creates in-memory storage primitives for broker runtime use.
        """
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def build_key(team_id: str, channel_id: str, thread_ts: str) -> str:
        """Create a deterministic unique key from Slack thread coordinates.

        Why this approach:
        team, channel, and thread timestamp together uniquely identify a
        conversation context across command and message events.

        Args:
            team_id: Slack workspace identifier.
            channel_id: Slack channel or DM identifier.
            thread_ts: Slack thread timestamp.

        Returns:
            str: Composite session key used in the in-memory index.
        """
        return f"{team_id}:{channel_id}:{thread_ts}"

    async def upsert(
        self,
        team_id: str,
        channel_id: str,
        thread_ts: str,
        user_id: str | None = None,
    ) -> ConversationSession:
        """Create or refresh a session for the given thread.

        Why this approach:
        using one upsert path avoids duplicate thread records and updates
        ``last_activity_at`` consistently for sweeper expiry checks.

        Args:
            team_id: Slack workspace identifier.
            channel_id: Slack channel or DM identifier.
            thread_ts: Slack thread timestamp.
            user_id: Optional user identifier for attribution updates.

        Returns:
            ConversationSession: The created or existing session object.
        """
        async with self._lock:
            key = self.build_key(team_id, channel_id, thread_ts)
            session = self._sessions.get(key)
            if session is None:
                session = ConversationSession(
                    key=key,
                    team_id=team_id,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    user_id=user_id,
                )
                self._sessions[key] = session
            else:
                session.last_activity_at = time.time()
                if user_id:
                    session.user_id = user_id
            return session

    async def get(self, key: str) -> ConversationSession | None:
        """Fetch a session by key.

        Args:
            key: Composite session key created by ``build_key``.

        Returns:
            ConversationSession | None: Session when found, else ``None``.
        """
        async with self._lock:
            return self._sessions.get(key)

    async def update(self, key: str, **kwargs: Any) -> ConversationSession | None:
        """Apply partial field updates to an existing session.

        Why this approach:
        flexible keyword updates keep handler code concise while preserving one
        lock-protected mutation point.

        Args:
            key: Composite session key identifying the target session.
            **kwargs: Session attributes and values to set.

        Returns:
            ConversationSession | None: Updated session or ``None`` if missing.
        """
        async with self._lock:
            session = self._sessions.get(key)
            if session is None:
                return None
            for k, v in kwargs.items():
                setattr(session, k, v)
            session.last_activity_at = time.time()
            return session

    async def delete(self, key: str) -> None:
        """Delete a session if it exists.

        Args:
            key: Composite session key identifying the target session.

        Returns:
            None: Removes the session entry when present.
        """
        async with self._lock:
            self._sessions.pop(key, None)

    async def all_sessions(self) -> list[ConversationSession]:
        """Return a snapshot list of all active sessions.

        Why this approach:
        a shallow copy avoids callers mutating internal storage while allowing
        the sweeper to iterate safely outside the manager lock.

        Returns:
            list[ConversationSession]: Snapshot of current sessions.
        """
        async with self._lock:
            return list(self._sessions.values())
