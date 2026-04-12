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

from datetime import datetime, timedelta, timezone

from opamp_provider.proto import opamp_pb2
from opamp_provider.state import ClientRecord, ClientStore


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


def test_client_version_persists_when_later_message_omits_description() -> None:
    """Verify client version is retained when a subsequent message omits `agent_description`."""
    store = ClientStore()
    first = opamp_pb2.AgentToServer(instance_uid=b"\x0e\x0f")
    first.sequence_num = 1
    version = first.agent_description.identifying_attributes.add()
    version.key = "service.version"
    version.value.string_value = "2.3.4"

    record = store.upsert_from_agent_msg(first)
    assert record.client_version == "2.3.4"

    second = opamp_pb2.AgentToServer(instance_uid=b"\x0e\x0f")
    second.sequence_num = 2
    record = store.upsert_from_agent_msg(second)

    assert record.client_version == "2.3.4"


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


def test_client_record_json_dump_serializes_pending_identification_as_hex() -> None:
    """Verify JSON model dumping serializes pending agent-identification bytes as a hex string."""
    record = ClientRecord(
        client_id="client-hex",
        pending_agent_identification=b"\x01\x9d",
    )

    dumped = record.model_dump(mode="json")

    assert dumped["pending_agent_identification"] == "019d"


def test_identification_rekeys_existing_client_record() -> None:
    """Verify server-issued identification rekeys the existing client record instead of duplicating it."""
    store = ClientStore()
    old_uid = bytes.fromhex("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    new_uid = bytes.fromhex("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    first = opamp_pb2.AgentToServer(instance_uid=old_uid)
    first.sequence_num = 1
    version = first.agent_description.identifying_attributes.add()
    version.key = "service.version"
    version.value.string_value = "9.9.9"
    record = store.upsert_from_agent_msg(first)
    old_client_id = record.client_id
    assert old_client_id == old_uid.hex()

    updated = store.set_agent_identification(old_client_id, new_uid)
    assert updated is not None
    assert store.pop_agent_identification(old_client_id) == new_uid

    second = opamp_pb2.AgentToServer(instance_uid=new_uid)
    second.sequence_num = 2
    rekeyed = store.upsert_from_agent_msg(second)

    assert rekeyed.client_id == new_uid.hex()
    assert rekeyed.message_id == 2
    assert rekeyed.client_version == "9.9.9"
    assert store.get(old_client_id) is None
    assert store.get(new_uid.hex()) is rekeyed


def test_pending_approval_capture_and_approve_flow() -> None:
    """Verify pending-approval records capture first payload details and can be approved."""
    store = ClientStore()
    uid = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
    msg = opamp_pb2.AgentToServer(instance_uid=uid)
    msg.sequence_num = 17
    instance_id = msg.agent_description.identifying_attributes.add()
    instance_id.key = "service.instance.id"
    instance_id.value.string_value = "agent-17"
    version = msg.agent_description.identifying_attributes.add()
    version.key = "service.version"
    version.value.string_value = "1.2.3"

    pending = store.add_pending_approval_from_agent_msg(
        msg,
        channel="HTTP",
        remote_addr="10.0.0.10",
    )

    assert pending.client_id == uid.hex()
    assert pending.message_id == 17
    assert pending.client_version == "1.2.3"
    assert pending.remote_addr == "10.0.0.10"
    assert store.pending_approval_count() == 1
    assert store.known_client(uid.hex()) is False

    approved = store.approve_pending_approval(uid.hex())
    assert approved is not None
    assert approved.client_id == uid.hex()
    assert store.pending_approval_count() == 0
    assert store.known_client(uid.hex()) is True


def test_block_agent_clears_pending_and_marks_blocked() -> None:
    """Verify blocking an agent removes pending approval state and marks blocked membership."""
    store = ClientStore()
    uid = bytes.fromhex("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1")
    msg = opamp_pb2.AgentToServer(instance_uid=uid)
    msg.sequence_num = 1
    store.add_pending_approval_from_agent_msg(msg, channel="HTTP")

    store.block_agent(
        uid.hex(),
        reason="manual block",
        headers={"x-test": "blocked"},
    )

    assert store.pending_approval_count() == 0
    assert store.is_blocked_agent(uid.hex()) is True
    assert uid.hex() in store.list_blocked_agents()


def test_export_persisted_state_blocked_entries_are_allowlisted() -> None:
    """Verify persisted blocked-agent entries only include instance_uid, ip, and blocked_at."""
    store = ClientStore()
    uid = "abcabcabcabcabcabcabcabcabcabcab"
    store.block_agent(
        uid,
        reason="manual block",
        headers={"Authorization": "Bearer token"},
        ip="203.0.113.7",
    )

    payload = store.export_persisted_state()

    blocked = payload["blocked_agents"]
    assert isinstance(blocked, list)
    assert len(blocked) == 1
    entry = blocked[0]
    assert set(entry.keys()) == {"instance_uid", "ip", "blocked_at"}
    assert entry["instance_uid"] == uid
    assert entry["ip"] == "203.0.113.7"
    assert isinstance(entry["blocked_at"], str)


def test_import_persisted_state_ignores_unknown_and_queues_refresh_for_missing() -> None:
    """Verify restore ignores unknown fields and queues force-resync for incomplete records with valid UIDs."""
    store = ClientStore()
    client_id = "1234567890abcdef1234567890abcdef"
    provider_state = {
        "default_heartbeat_frequency": 30,
        "clients": [
            {
                "client_id": client_id,
                "unknown_future_field": "ignored",
            }
        ],
        "pending_approvals": [],
        "blocked_agents": [],
        "pending_instance_uid_replacements": {},
    }

    summary = store.import_persisted_state(provider_state)
    restored = store.get(client_id)

    assert restored is not None
    assert summary["clients"] == 1
    assert summary["unknown_attributes_ignored"] >= 1
    assert summary["full_refresh_queued"] == 1
    assert len(restored.commands) >= 1
    assert restored.commands[-1].action == "forceresync"
