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

"""Event history model used for timeline entries in client history."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class EventHistory(BaseModel):
    """Represents one history event with immutable creation metadata."""

    model_config = ConfigDict(frozen=False)

    event_time: datetime = Field(default_factory=_utc_now)
    event_description: str

    def get_event_time(self) -> datetime:
        """Return the timestamp assigned when the event object was created."""
        return self.event_time

    def get_event_description(self) -> str:
        """Return the description assigned when the event object was created."""
        return self.event_description
