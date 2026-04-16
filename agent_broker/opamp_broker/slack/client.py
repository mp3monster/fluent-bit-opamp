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

"""Slack Bolt client factory and socket mode bootstrap helpers.

Keeping creation and start logic in one small module simplifies mocking these
integration boundaries during broker entrypoint unit tests.
"""

from __future__ import annotations

import logging

import httpx
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

try:
    from slack_sdk.errors import SlackApiError
except ImportError:  # pragma: no cover - allows tests without slack_sdk installed.
    class SlackApiError(Exception):
        """Fallback Slack API error type used when slack_sdk is unavailable."""

logger = logging.getLogger(__name__)
SLACK_APPS_CONNECTIONS_OPEN_URL = "https://slack.com/api/apps.connections.open"


def create_app(bot_token: str, signing_secret: str) -> AsyncApp:
    """Build an async Slack Bolt application instance.

    Why this wrapper:
    centralizing creation makes dependency wiring explicit and test patching
    straightforward from the broker entrypoint.

    Args:
        bot_token: Slack bot OAuth token.
        signing_secret: Slack app signing secret for request verification.

    Returns:
        AsyncApp: Configured Slack Bolt async application.
    """
    return AsyncApp(token=bot_token, signing_secret=signing_secret)


async def start_socket_mode(app: AsyncApp, app_token: str) -> None:
    """Start Slack Socket Mode event delivery for the provided app.

    Args:
        app: Slack Bolt async app with registered handlers.
        app_token: Slack app-level token for Socket Mode connection.

    Returns:
        None: Runs the socket-mode handler until cancelled or disconnected.
    """
    handler = AsyncSocketModeHandler(app, app_token)
    try:
        verification = await verify_slack_connection(app, app_token)
        logger.info(
            "***** Successfully connected to Slack (team=%s, bot_user=%s, bot_id=%s) *****",
            verification.get("team", "unknown"),
            verification.get("user", "unknown"),
            verification.get("bot_id", "unknown"),
        )
        await handler.start_async()
    except SlackApiError as exc:
        response = getattr(exc, "response", None)
        slack_error = (
            response.get("error", "unknown_error")
            if response is not None
            else str(exc)
        )
        logger.error(
            "***** Failed to connect to Slack: %s *****",
            slack_error,
            exc_info=True,
        )
        raise
    except Exception as exc:
        logger.error(
            "***** Failed to connect to Slack: %s *****",
            str(exc),
            exc_info=True,
        )
        raise


async def verify_slack_connection(app: AsyncApp, app_token: str) -> dict[str, str]:
    """Verify bot token auth and app token socket-mode connectivity."""
    auth_response = await app.client.auth_test()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            SLACK_APPS_CONNECTIONS_OPEN_URL,
            headers={"Authorization": f"Bearer {app_token}"},
        )
        response.raise_for_status()
        payload = response.json()

    if not payload.get("ok"):
        raise RuntimeError(
            f"Slack apps.connections.open failed: {payload.get('error', 'unknown_error')}"
        )

    return {
        "team": str(auth_response.get("team", "unknown")),
        "user": str(auth_response.get("user", "unknown")),
        "bot_id": str(auth_response.get("bot_id", "unknown")),
    }
