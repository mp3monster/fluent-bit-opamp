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

"""Slack-backed social collaboration adapter implementation."""

from __future__ import annotations

import logging
import os
from typing import Any

from opamp_broker.session.manager import SessionManager
from opamp_broker.slack.client import (
    create_app,
    start_socket_mode,
    verify_slack_connection,
)
from opamp_broker.slack.handlers import register_handlers
from opamp_broker.social_collaboration.base import SocialCollaborationAdapter

ENV_SLACK_BOT_TOKEN = "SLACK_BOT_TOKEN"
ENV_SLACK_SIGNING_SECRET = "SLACK_SIGNING_SECRET"
ENV_SLACK_APP_TOKEN = "SLACK_APP_TOKEN"
logger = logging.getLogger(__name__)


class SlackSocialCollaborationAdapter(SocialCollaborationAdapter):
    """Adapter that maps broker social collaboration operations onto Slack."""

    def __init__(self, bot_token: str, signing_secret: str, app_token: str) -> None:
        self._app = create_app(bot_token, signing_secret)
        self._app_token = app_token

    @classmethod
    def from_environment(cls) -> "SlackSocialCollaborationAdapter":
        """Create a Slack adapter using required runtime environment variables."""
        return cls(
            bot_token=os.environ[ENV_SLACK_BOT_TOKEN],
            signing_secret=os.environ[ENV_SLACK_SIGNING_SECRET],
            app_token=os.environ[ENV_SLACK_APP_TOKEN],
        )

    def register_handlers(
        self,
        session_manager: SessionManager,
        compiled_graph: Any,
        config: dict[str, Any],
    ) -> None:
        """Register Slack command/event handlers."""
        register_handlers(self._app, session_manager, compiled_graph, config)

    async def start(self) -> None:
        """Start Slack Socket Mode event delivery."""
        await start_socket_mode(self._app, self._app_token)

    async def post_message(self, *, channel_id: str, thread_ts: str, text: str) -> None:
        """Send a message reply into a specific Slack thread."""
        await self._app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
        )

    async def verify_connection(self) -> dict[str, Any]:
        """Verify Slack bot and app-token connectivity for startup diagnostics."""
        try:
            verification = await verify_slack_connection(self._app, self._app_token)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        logger.info(
            "***** Slack connection verification succeeded (team=%s, bot_user=%s, bot_id=%s) *****",
            verification.get("team", "unknown"),
            verification.get("user", "unknown"),
            verification.get("bot_id", "unknown"),
        )
        return {
            "ok": True,
            "message": "Slack connection verified successfully.",
            **verification,
        }
