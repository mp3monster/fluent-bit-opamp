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

from opamp_broker.session.manager import SessionManager

logger = logging.getLogger(__name__)


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
        config.get("messages", {})
        if isinstance(config, dict)
        else {}
    )
    help_text = str(
        message_config.get(
            "help",
            "Try `/opamp status collector-a`, `/opamp health collector-a`, "
            "or mention me with a question.",
        )
    )
    slack_error_reply = str(
        message_config.get(
            "slack_error_reply",
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
        event = body.get("event", {})
        team_id = body.get("team_id") or body.get("authorizations", [{}])[0].get("team_id", "unknown")
        channel_id = event.get("channel") or body.get("channel_id")
        ts = event.get("thread_ts") or event.get("ts") or body.get("trigger_id", "no-thread")
        user_id = event.get("user") or body.get("user_id")
        try:
            session = await session_manager.upsert(team_id, channel_id, ts, user_id)
            result = await compiled_graph.ainvoke(
                {
                    "team_id": team_id,
                    "channel_id": channel_id,
                    "thread_ts": ts,
                    "user_id": user_id or "",
                    "text": text,
                }
            )

            await session_manager.update(
                session.key,
                current_target=result.get("target"),
                environment=result.get("environment"),
                intent=result.get("intent"),
                last_summary=result.get("response_text"),
                pending_action=(
                    {"tool": result.get("tool_name"), "args": result.get("tool_args")}
                    if result.get("requires_confirmation")
                    else None
                ),
            )
            await say(text=result.get("response_text", help_text), thread_ts=ts)
        except Exception:
            logger.exception(
                "failed processing Slack message event",
                extra={
                    "event": "slack.handlers.message_processing_failed",
                    "context": {
                        "team_id": team_id,
                        "channel_id": channel_id,
                        "thread_ts": ts,
                    },
                },
            )
            with suppress(Exception):
                await say(text=slack_error_reply, thread_ts=ts)

    @app.command(config["slack"]["command_name"])
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
        text = body.get("text", "").strip()
        if not text:
            await respond(help_text)
            return

        team_id = body.get("team_id", "unknown")
        channel_id = body.get("channel_id", "unknown")
        thread_ts = body.get("thread_ts") or body.get("message_ts") or body.get("trigger_id", "slash")
        user_id = body.get("user_id")
        try:
            session = await session_manager.upsert(team_id, channel_id, thread_ts, user_id)

            result = await compiled_graph.ainvoke(
                {
                    "team_id": team_id,
                    "channel_id": channel_id,
                    "thread_ts": thread_ts,
                    "user_id": user_id or "",
                    "text": text,
                }
            )

            await session_manager.update(
                session.key,
                current_target=result.get("target"),
                environment=result.get("environment"),
                intent=result.get("intent"),
                last_summary=result.get("response_text"),
                pending_action=(
                    {"tool": result.get("tool_name"), "args": result.get("tool_args")}
                    if result.get("requires_confirmation")
                    else None
                ),
            )
            await respond(text=result.get("response_text", help_text), response_type="ephemeral")
        except Exception:
            logger.exception(
                "failed handling Slack slash command",
                extra={
                    "event": "slack.handlers.command_failed",
                    "context": {
                        "team_id": team_id,
                        "channel_id": channel_id,
                        "thread_ts": thread_ts,
                        "command": config["slack"]["command_name"],
                    },
                },
            )
            with suppress(Exception):
                await respond(text=slack_error_reply, response_type="ephemeral")

    @app.event("app_mention")
    async def handle_mention(body: dict[str, Any], say: Any) -> None:
        """Handle app mentions in channels by delegating to message processing.

        Args:
            body: Slack event envelope for the mention.
            say: Slack Bolt responder bound to the source channel/thread.

        Returns:
            None: Posts graph output back to the mention thread.
        """
        text = body.get("event", {}).get("text", "")
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
        channel_type = event.get("channel_type")
        if channel_type != "im":
            return
        text = event.get("text", "")
        await _process_message(body, text, say)
