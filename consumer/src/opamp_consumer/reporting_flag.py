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

"""Reporting flag enumeration shared by OpAMP consumer components."""

from __future__ import annotations

from enum import Enum

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - Python <3.11 fallback

    class StrEnum(str, Enum):
        """Compatibility fallback for Python versions without enum.StrEnum."""


class ReportingFlag(StrEnum):
    """Enumeration of provider-directed reporting controls."""

    REPORT_HEALTH = "reportHealth"
    REPORT_CAPABILITIES = "reportCapabilities"
    REPORT_CUSTOM_CAPABILITIES = "reportCustomCapabilities"
    REPORT_DESCRIPTION = "reportDescription"

    @classmethod
    def set_all_reporting_flags(
        cls,
        reporting_flags: dict["ReportingFlag", bool],
        value: bool = True,
    ) -> None:
        """Set all reporting-flag dictionary values to the provided boolean."""
        for flag in cls:
            reporting_flags[flag] = value

