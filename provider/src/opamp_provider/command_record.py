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

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CommandRecord(BaseModel):
    """Represents a queued command and its dispatch timestamps."""

    model_config = ConfigDict(frozen=False)

    command: str
    classifier: str
    action: str
    key_value_pairs: list[dict[str, str]] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=_utc_now)
    sent_at: Optional[datetime] = None
