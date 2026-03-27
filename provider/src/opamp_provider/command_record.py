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

"""Command record model for queued client commands."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import ConfigDict, Field, model_validator

from opamp_provider.event_history import EventHistory


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CommandRecord(EventHistory):
    """Represents a queued command and its dispatch timestamps."""

    model_config = ConfigDict(frozen=False)

    classifier: str = Field(
        description="Command classifier used to route payload construction."
    )
    action: str = Field(description="Command action value sent to the target agent.")
    key_value_pairs: list[dict[str, str]] = Field(
        default_factory=list,
        description="Normalized command parameters stored as key/value pairs.",
    )
    received_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when the command was queued by the provider.",
    )
    sent_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the command was transmitted to the agent.",
    )

    @model_validator(mode="before")
    @classmethod
    def _align_event_and_received_times(cls, data: object) -> object:
        """Use one creation timestamp for command receipt and event timeline entry."""
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if payload.get("received_at") is None:
            payload["received_at"] = _utc_now()
        if payload.get("event_time") is None:
            payload["event_time"] = payload["received_at"]
        return payload
