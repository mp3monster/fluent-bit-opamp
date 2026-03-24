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

from datetime import timedelta, timezone, datetime

from opamp_provider.state import ClientStore
from opamp_provider.proto import opamp_pb2


def test_disconnect_marks_and_purges() -> None:
    """Verify disconnect lifecycle by upserting an `agent_disconnect` message, aging the timestamp, then asserting purge removes the record."""
    store = ClientStore()
    msg = opamp_pb2.AgentToServer(instance_uid=b"\x01\x02")
    msg.agent_disconnect.SetInParent()

    record = store.upsert_from_agent_msg(msg)
    assert record.disconnected is True
    assert record.disconnected_at is not None

    record.disconnected_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    removed = store.purge_disconnected(datetime.now(timezone.utc) - timedelta(minutes=30))

    assert len(removed) == 1
    assert store.get(record.client_id) is None


def test_custom_capabilities_are_stored_from_agent_message() -> None:
    """Verify capability deduplication/filtering by upserting repeated and empty capabilities and asserting normalized stored values."""
    store = ClientStore()
    msg = opamp_pb2.AgentToServer(instance_uid=b"\x0a\x0b")
    msg.custom_capabilities.capabilities.extend(
        [
            "org.mp3monster.opamp_provider.chatopcommand",
            "org.mp3monster.opamp_provider.command_shutdown_agent",
            "org.mp3monster.opamp_provider.chatopcommand",
            "",
        ]
    )

    record = store.upsert_from_agent_msg(msg)

    assert record.custom_capabilities_reported == [
        "org.mp3monster.opamp_provider.chatopcommand",
        "org.mp3monster.opamp_provider.command_shutdown_agent",
    ]


def test_custom_capabilities_strip_request_status_prefix() -> None:
    """Verify `request:` capability prefixes are normalized by upserting prefixed values and asserting stripped stored capabilities."""
    store = ClientStore()
    msg = opamp_pb2.AgentToServer(instance_uid=b"\x0c\x0d")
    msg.custom_capabilities.capabilities.extend(
        [
            "request:org.mp3monster.opamp_provider.chatopcommand",
            "request:org.mp3monster.opamp_provider.command_shutdown_agent",
        ]
    )

    record = store.upsert_from_agent_msg(msg)

    assert record.custom_capabilities_reported == [
        "org.mp3monster.opamp_provider.chatopcommand",
        "org.mp3monster.opamp_provider.command_shutdown_agent",
    ]
