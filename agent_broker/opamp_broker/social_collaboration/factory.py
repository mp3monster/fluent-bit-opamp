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

"""Factory helpers for selecting social collaboration adapter implementations."""

from __future__ import annotations

from opamp_broker.social_collaboration.base import SocialCollaborationAdapter
from opamp_broker.social_collaboration.adapters.slack import (
    SlackSocialCollaborationAdapter,
)

SUPPORTED_SOCIAL_COLLABORATION_IMPLEMENTATIONS = ("slack",)


def create_social_collaboration_adapter(
    implementation: str,
) -> SocialCollaborationAdapter:
    """Build a social collaboration adapter for the requested implementation."""
    normalized = str(implementation or "slack").strip().lower()
    if normalized == "slack":
        return SlackSocialCollaborationAdapter.from_environment()
    supported = ", ".join(SUPPORTED_SOCIAL_COLLABORATION_IMPLEMENTATIONS)
    raise ValueError(
        f"unsupported social collaboration implementation '{implementation}'; "
        f"supported values: {supported}"
    )
