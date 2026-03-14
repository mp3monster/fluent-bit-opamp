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

from opamp_provider.proto import opamp_pb2, anyvalue_pb2
from opamp_provider.state import ClientStore


def _agent_message(*, instance_uid: bytes, version: str | None = None) -> opamp_pb2.AgentToServer:
    msg = opamp_pb2.AgentToServer(instance_uid=instance_uid)
    msg.capabilities = (
        opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus
        | opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsHealth
    )
    if version is not None:
        kv = anyvalue_pb2.KeyValue(
            key="service.version",
            value=anyvalue_pb2.AnyValue(string_value=version),
        )
        msg.agent_description.identifying_attributes.append(kv)
    return msg


def test_upsert_from_agent_msg_sets_state() -> None:
    store = ClientStore()
    msg = _agent_message(instance_uid=b"abc", version="1.2.3")
    record = store.upsert_from_agent_msg(msg)

    assert record.client_id == "616263"
    assert record.last_communication is not None
    assert record.node_age_seconds is not None
    assert record.agent_description is not None
    assert record.client_version == "1.2.3"
    assert "AgentCapabilities_ReportsStatus" in record.capabilities
    assert "AgentCapabilities_ReportsHealth" in record.capabilities


def test_command_queue_and_send() -> None:
    store = ClientStore()
    client_id = "client-1"

    cmd = store.queue_command(client_id, "restart")
    pending = store.next_pending_command(client_id)
    assert pending is cmd
    assert pending.sent_at is None

    store.mark_command_sent(client_id, pending)
    assert pending.sent_at is not None
    assert store.next_pending_command(client_id) is None
