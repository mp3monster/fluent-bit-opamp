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

"""Slack event and command handlers that drive broker conversation flow.

This module adapts Slack payloads into graph state, updates session snapshots,
and emits thread responses with a consistent output contract.
"""

from __future__ import annotations

from contextlib import suppress
import logging
from typing import Any

from slack_bolt.async_app import AsyncApp

from opamp_broker.graph.state import (
    STATE_KEY_CHANNEL_ID,
    STATE_KEY_INTENT,
    STATE_KEY_TARGET,
    STATE_KEY_TEAM_ID,
    STATE_KEY_TEXT,
    STATE_KEY_THREAD_TS,
    STATE_KEY_TOOL_ARGS,
    STATE_KEY_TOOL_NAME,
    STATE_KEY_USER_ID,
)
from opamp_broker.session.manager import SessionManager

logger = logging.getLogger(__name__)
CONFIG_KEY_MESSAGES = "messages"
CONFIG_KEY_SLACK = "slack"
CONFIG_KEY_COMMAND_NAME = "command_name"
MESSAGE_KEY_HELP = "help"
MESSAGE_KEY_SLACK_ERROR_REPLY = "slack_error_reply"
SLACK_KEY_EVENT = "event"
SLACK_KEY_TEAM_ID = "team_id"
SLACK_KEY_AUTHORIZATIONS = "authorizations"
SLACK_KEY_CHANNEL = "channel"
SLACK_KEY_CHANNEL_ID = "channel_id"
SLACK_KEY_THREAD_TS = "thread_ts"
SLACK_KEY_TS = "ts"
SLACK_KEY_TRIGGER_ID = "trigger_id"
SLACK_KEY_USER = "user"
SLACK_KEY_USER_ID = "user_id"
SLACK_KEY_TEXT = "text"
SLACK_KEY_MESSAGE_TS = "message_ts"
SLACK_KEY_CHANNEL_TYPE = "channel_type"
SLACK_KEY_RESPONSE_TEXT = "response_text"
SLACK_KEY_ENVIRONMENT = "environment"
SLACK_KEY_REQUIRES_CONFIRMATION = "requires_confirmation"
SLACK_KEY_PENDING_ACTION_TOOL = "tool"
SLACK_KEY_PENDING_ACTION_ARGS = "args"
SLACK_KEY_UNKNOWN = "unknown"
SLACK_KEY_NO_THREAD = "no-thread"
SLACK_KEY_SLASH = "slash"
SLACK_KEY_EPHEMERAL = "ephemeral"
SLACK_CHANNEL_TYPE_IM = "im"
LOG_KEY_EVENT = "event"
LOG_KEY_CONTEXT = "context"
LOG_KEY_COMMAND = "command"


def register_handlers(
    app: AsyncApp,
    session_manager: SessionManager,
    compiled_graph: Any,
    config: dict[str, Any],
) -> None:
    """Register slash-command, mention, and DM handlers on the Slack app.

    Why this approach:
    colocating registration keeps shared helpers (session updates and graph
    invocation) close to the handlers that use them.

    Args:
        app: Slack Bolt async application receiving events.
        session_manager: Session storage used to persist thread context.
        compiled_graph: LangGraph runnable used to process user requests.
        config: Runtime broker configuration including message templates.

    Returns:
        None: Handlers are registered by side effect on ``app``.
    """
    message_config = (
        config.get(CONFIG_KEY_MESSAGES, {})
        if isinstance(config, dict)
        else {}
    )
    help_text = str(
        message_config.get(
            MESSAGE_KEY_HELP,
            "Try `/opamp status collector-a`, `/opamp health collector-a`, "
            "or mention me with a question.",
        )
    )
    slack_error_reply = str(
        message_config.get(
            MESSAGE_KEY_SLACK_ERROR_REPLY,
            "sorry a bit dizzy at the moment",
        )
    ).strip() or "sorry a bit dizzy at the moment"

    async def _process_message(body: dict[str, Any], text: str, say: Any) -> None:
        """Process a conversational message event and post graph output.

        Why this helper:
        app mentions and DMs share nearly identical processing, so one helper
        avoids duplicated state construction and session bookkeeping.

        Args:
            body: Slack event envelope containing metadata and event payload.
            text: Message text to route through the conversation graph.
            say: Slack Bolt responder bound to the source context.

        Returns:
            None: Updates session state and posts a threaded response.
        """
        event = body.get(SLACK_KEY_EVENT, {})
        team_id = body.get(SLACK_KEY_TEAM_ID) or body.get(
            SLACK_KEY_AUTHORIZATIONS,
            [{}],
        )[0].get(SLACK_KEY_TEAM_ID, SLACK_KEY_UNKNOWN)
        channel_id = event.get(SLACK_KEY_CHANNEL) or body.get(SLACK_KEY_CHANNEL_ID)
        ts = (
            event.get(SLACK_KEY_THREAD_TS)
            or event.get(SLACK_KEY_TS)
            or body.get(SLACK_KEY_TRIGGER_ID, SLACK_KEY_NO_THREAD)
        )
        user_id = event.get(SLACK_KEY_USER) or body.get(SLACK_KEY_USER_ID)
        try:
            session = await session_manager.upsert(team_id, channel_id, ts, user_id)
            result = await compiled_graph.ainvoke(
                {
                    STATE_KEY_TEAM_ID: team_id,
                    STATE_KEY_CHANNEL_ID: channel_id,
                    STATE_KEY_THREAD_TS: ts,
                    STATE_KEY_USER_ID: user_id or "",
                    STATE_KEY_TEXT: text,
                }
            )

            await session_manager.update(
                session.key,
                current_target=result.get(STATE_KEY_TARGET),
                environment=result.get(SLACK_KEY_ENVIRONMENT),
                intent=result.get(STATE_KEY_INTENT),
                last_summary=result.get(SLACK_KEY_RESPONSE_TEXT),
                pending_action=(
                    {
                        SLACK_KEY_PENDING_ACTION_TOOL: result.get(STATE_KEY_TOOL_NAME),
                        SLACK_KEY_PENDING_ACTION_ARGS: result.get(STATE_KEY_TOOL_ARGS),
                    }
                    if result.get(SLACK_KEY_REQUIRES_CONFIRMATION)
                    else None
                ),
            )
            await say(text=result.get(SLACK_KEY_RESPONSE_TEXT, help_text), thread_ts=ts)
        except Exception:
            logger.exception(
                "failed processing Slack message event",
                extra={
                    LOG_KEY_EVENT: "slack.handlers.message_processing_failed",
                    LOG_KEY_CONTEXT: {
                        SLACK_KEY_TEAM_ID: team_id,
                        SLACK_KEY_CHANNEL_ID: channel_id,
                        SLACK_KEY_THREAD_TS: ts,
                    },
                },
            )
            with suppress(Exception):
                await say(text=slack_error_reply, thread_ts=ts)

    @app.command(config[CONFIG_KEY_SLACK][CONFIG_KEY_COMMAND_NAME])
    async def handle_command(ack: Any, body: dict[str, Any], respond: Any) -> None:
        """Handle `/opamp` commands and return an ephemeral response.

        Why this flow:
        slash commands should acknowledge quickly and reply ephemerally so user
        prompts do not spam channels while still preserving thread context.

        Args:
            ack: Slack acknowledgment callable for command receipt.
            body: Slash command payload from Slack.
            respond: Slack response callable for command replies.

        Returns:
            None: Acknowledges, updates session state, and sends a response.
        """
        await ack()
        text = body.get(SLACK_KEY_TEXT, "").strip()
        if not text:
            await respond(help_text)
            return

        team_id = body.get(SLACK_KEY_TEAM_ID, SLACK_KEY_UNKNOWN)
        channel_id = body.get(SLACK_KEY_CHANNEL_ID, SLACK_KEY_UNKNOWN)
        thread_ts = (
            body.get(SLACK_KEY_THREAD_TS)
            or body.get(SLACK_KEY_MESSAGE_TS)
            or body.get(SLACK_KEY_TRIGGER_ID, SLACK_KEY_SLASH)
        )
        user_id = body.get(SLACK_KEY_USER_ID)
        try:
            session = await session_manager.upsert(team_id, channel_id, thread_ts, user_id)

            result = await compiled_graph.ainvoke(
                {
                    STATE_KEY_TEAM_ID: team_id,
                    STATE_KEY_CHANNEL_ID: channel_id,
                    STATE_KEY_THREAD_TS: thread_ts,
                    STATE_KEY_USER_ID: user_id or "",
                    STATE_KEY_TEXT: text,
                }
            )

            await session_manager.update(
                session.key,
                current_target=result.get(STATE_KEY_TARGET),
                environment=result.get(SLACK_KEY_ENVIRONMENT),
                intent=result.get(STATE_KEY_INTENT),
                last_summary=result.get(SLACK_KEY_RESPONSE_TEXT),
                pending_action=(
                    {
                        SLACK_KEY_PENDING_ACTION_TOOL: result.get(STATE_KEY_TOOL_NAME),
                        SLACK_KEY_PENDING_ACTION_ARGS: result.get(STATE_KEY_TOOL_ARGS),
                    }
                    if result.get(SLACK_KEY_REQUIRES_CONFIRMATION)
                    else None
                ),
            )
            await respond(
                text=result.get(SLACK_KEY_RESPONSE_TEXT, help_text),
                response_type=SLACK_KEY_EPHEMERAL,
            )
        except Exception:
            logger.exception(
                "failed handling Slack slash command",
                extra={
                    LOG_KEY_EVENT: "slack.handlers.command_failed",
                    LOG_KEY_CONTEXT: {
                        SLACK_KEY_TEAM_ID: team_id,
                        SLACK_KEY_CHANNEL_ID: channel_id,
                        SLACK_KEY_THREAD_TS: thread_ts,
                        LOG_KEY_COMMAND: config[CONFIG_KEY_SLACK][CONFIG_KEY_COMMAND_NAME],
                    },
                },
            )
            with suppress(Exception):
                await respond(text=slack_error_reply, response_type=SLACK_KEY_EPHEMERAL)

    @app.event("app_mention")
    async def handle_mention(body: dict[str, Any], say: Any) -> None:
        """Handle app mentions in channels by delegating to message processing.

        Args:
            body: Slack event envelope for the mention.
            say: Slack Bolt responder bound to the source channel/thread.

        Returns:
            None: Posts graph output back to the mention thread.
        """
        text = body.get(SLACK_KEY_EVENT, {}).get(SLACK_KEY_TEXT, "")
        await _process_message(body, text, say)

    @app.event("message")
    async def handle_message(
        body: dict[str, Any], say: Any, event: dict[str, Any]
    ) -> None:
        """Handle direct-message events while ignoring non-DM traffic.

        Why this guard:
        channel message events are noisy; restricting this path to DM traffic
        prevents duplicate responses when app mentions already handle channels.

        Args:
            body: Slack event envelope.
            say: Slack Bolt responder bound to the event context.
            event: Flattened event payload supplied by Bolt.

        Returns:
            None: Processes DM text through the conversation graph when eligible.
        """
        channel_type = event.get(SLACK_KEY_CHANNEL_TYPE)
        if channel_type != SLACK_CHANNEL_TYPE_IM:
            return
        text = event.get(SLACK_KEY_TEXT, "")
        await _process_message(body, text, say)
