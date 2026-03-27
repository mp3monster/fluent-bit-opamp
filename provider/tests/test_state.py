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


def test_check_sequence_num_initial_message_queues_force_resync() -> None:
    """Verify first-seen message ID queues force-resync and stores the received sequence number."""
    store = ClientStore()
    msg = opamp_pb2.AgentToServer(instance_uid=b"\x01\x10")
    msg.sequence_num = 10

    record = store.upsert_from_agent_msg(msg)

    assert record.message_id == 10
    assert len(record.commands) == 1
    command = record.commands[0]
    assert command.classifier == "command"
    assert command.action == "forceresync"
    assert command.sent_at is None


def test_check_sequence_num_sequential_message_does_not_queue_force_resync() -> None:
    """Verify a strictly sequential message ID does not queue an extra force-resync command."""
    store = ClientStore()
    first = opamp_pb2.AgentToServer(instance_uid=b"\x01\x11")
    first.sequence_num = 100
    record = store.upsert_from_agent_msg(first)
    assert len(record.commands) == 1
    record.commands[0].sent_at = datetime.now(timezone.utc)

    second = opamp_pb2.AgentToServer(instance_uid=b"\x01\x11")
    second.sequence_num = 101
    record = store.upsert_from_agent_msg(second)

    assert record.message_id == 101
    assert len(record.commands) == 1


def test_check_sequence_num_gap_queues_force_resync() -> None:
    """Verify non-sequential message IDs queue force-resync through the command mechanism."""
    store = ClientStore()
    first = opamp_pb2.AgentToServer(instance_uid=b"\x01\x12")
    first.sequence_num = 7
    record = store.upsert_from_agent_msg(first)
    assert len(record.commands) == 1
    record.commands[0].sent_at = datetime.now(timezone.utc)

    gap = opamp_pb2.AgentToServer(instance_uid=b"\x01\x12")
    gap.sequence_num = 9
    record = store.upsert_from_agent_msg(gap)

    assert record.message_id == 9
    assert len(record.commands) == 2
    assert record.commands[-1].action == "forceresync"
    assert record.commands[-1].sent_at is None


def test_set_client_heartbeat_frequency_updates_single_record_and_adds_event() -> None:
    """Verify per-client heartbeat update changes one client record and appends the heartbeat event."""
    store = ClientStore()
    first = opamp_pb2.AgentToServer(instance_uid=b"\x02\x01")
    first.sequence_num = 1
    second = opamp_pb2.AgentToServer(instance_uid=b"\x02\x02")
    second.sequence_num = 1
    first_record = store.upsert_from_agent_msg(first)
    second_record = store.upsert_from_agent_msg(second)

    updated = store.set_client_heartbeat_frequency(
        first_record.client_id,
        90,
        max_events=50,
    )

    assert updated is not None
    assert updated.heartbeat_frequency == 90
    assert second_record.heartbeat_frequency == 30
    assert updated.events[-1].get_event_description() == "send heartbeatfrequency event"
