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

import pytest

from opamp_provider.app import (
    ACTION_APPLY_CONFIG,
    ACTION_PACKAGE_AVAILABLE,
    app,
)
from opamp_provider import config as provider_config
from opamp_provider.config import ProviderConfig
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import STORE
from opamp_provider.transport import decode_message, encode_message


@pytest.mark.asyncio
async def test_http_endpoint() -> None:
    test_uid = b"1234567890abcdef"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=test_uid)
    agent_msg.capabilities = opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200
        payload = await resp.get_data()

    server_msg = opamp_pb2.ServerToAgent()
    server_msg.ParseFromString(payload)
    assert server_msg.instance_uid == test_uid


@pytest.mark.asyncio
async def test_websocket_endpoint() -> None:
    test_uid = b"abcdef1234567890"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=test_uid)
    agent_msg.capabilities = opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus

    async with app.test_client() as client:
        async with client.websocket("/v1/opamp") as ws:
            await ws.send(encode_message(agent_msg.SerializeToString()))
            data = await ws.receive()

    header, payload = decode_message(data)
    assert header == 0
    server_msg = opamp_pb2.ServerToAgent()
    server_msg.ParseFromString(payload)
    assert server_msg.instance_uid == test_uid


@pytest.mark.asyncio
async def test_get_comms_settings() -> None:
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.get("/api/settings/comms")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload == {
        "delayed_comms_seconds": 60,
        "significant_comms_seconds": 300,
    }


@pytest.mark.asyncio
async def test_put_comms_settings() -> None:
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={"delayed_comms_seconds": 120, "significant_comms_seconds": 600},
        )
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload == {
        "delayed_comms_seconds": 120,
        "significant_comms_seconds": 600,
    }


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid() -> None:
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={"delayed_comms_seconds": 300, "significant_comms_seconds": 60},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_queue_command_requires_payload() -> None:
    async with app.test_client() as client:
        resp = await client.post("/api/clients/client-1/commands")
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_queue_restart_command_and_emit_restart_payload() -> None:
    client_id = "000000000000000000000000000000ab"
    STORE._clients.clear()

    async with app.test_client() as client:
        queue_resp = await client.post(
            f"/api/clients/{client_id}/commands",
            json=[
                {"key": "classifier", "value": "command"},
                {"key": "action", "value": "restart"},
            ],
        )
        assert queue_resp.status_code == 201
        record = STORE.get(client_id)
        assert record is not None
        assert len(record.events) == 1
        event = record.events[0]
        event_desc = event.get_event_description()
        assert event_desc == "Restart Agent"

        agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
        opamp_resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert opamp_resp.status_code == 200
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await opamp_resp.get_data())
        assert server_msg.HasField("command")
        assert server_msg.command.type == opamp_pb2.CommandType.CommandType_Restart


@pytest.mark.asyncio
async def test_event_history_is_capped_to_configured_size() -> None:
    client_id = "000000000000000000000000000000cd"
    STORE._clients.clear()
    provider_config.set_config(
        ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=2,
        )
    )

    async with app.test_client() as client:
        for _ in range(3):
            resp = await client.post(
                f"/api/clients/{client_id}/commands",
                json=[
                    {"key": "classifier", "value": "command"},
                    {"key": "action", "value": "restart"},
                ],
            )
            assert resp.status_code == 201

    record = STORE.get(client_id)
    assert record is not None
    assert len(record.events) == 2


@pytest.mark.asyncio
async def test_queue_command_rejects_unsupported_classifier_action() -> None:
    async with app.test_client() as client:
        resp = await client.post(
            "/api/clients/client-1/commands",
            json=[
                {"key": "classifier", "value": "command"},
                {"key": "action", "value": "not-supported"},
            ],
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_custom_commands_returns_display_names_and_schema() -> None:
    async with app.test_client() as client:
        resp = await client.get("/api/commands/custom")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert "commands" in payload
    commands = payload["commands"]
    assert isinstance(commands, list)
    assert commands
    command_map = {entry["operation"]: entry for entry in commands}
    assert "chatopcommand" in command_map
    assert "nullcommand" in command_map
    assert "shutdownagent" in command_map
    first = command_map["chatopcommand"]
    assert first["fqdn"] == "org.mp3monster.opamp_provider.chatopcommand"
    assert first["displayname"] == "ChatOps Command"
    assert first["description"] == "custom chatopcommand queued"
    assert first["classifier"] == "custom"
    assert first["operation"] == "chatopcommand"
    assert isinstance(first["schema"], list)
    assert {
        "parametername": "action",
        "type": "string",
        "description": "Custom command operation name.",
        "isrequired": True,
    } in first["schema"]
    for row in first["schema"]:
        assert row.get("parametername") not in {"classifier", "type", "data"}
    shutdown = command_map["shutdownagent"]
    assert shutdown["fqdn"] == "org.mp3monster.opamp_provider.command_shutdown_agent"
    assert shutdown["displayname"] == "Shutdown Agent"
    assert shutdown["description"] == "custom shutdownagent queued"
    assert shutdown["schema"] == []
    nullcommand = command_map["nullcommand"]
    assert nullcommand["fqdn"] == "org.mp3monster.opamp_provider.nullcommand"
    assert nullcommand["displayname"] == "Null Command"
    assert nullcommand["description"] == "custom nullcommand queued"
    assert nullcommand["schema"] == []


@pytest.mark.asyncio
async def test_get_client_missing() -> None:
    async with app.test_client() as client:
        resp = await client.get("/api/clients/missing")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_client_actions_and_http_consumes() -> None:
    client_id = "1234"
    STORE._clients.clear()

    async with app.test_client() as client:
        resp = await client.post(
            f"/api/clients/{client_id}/actions",
            json={"actions": [ACTION_APPLY_CONFIG, ACTION_PACKAGE_AVAILABLE]},
        )
        assert resp.status_code == 200
        payload = await resp.get_json()
        assert payload["next_actions"] == [
            ACTION_APPLY_CONFIG,
            ACTION_PACKAGE_AVAILABLE,
        ]

        agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await resp.get_data())
        assert server_msg.HasField("remote_config")
        record = STORE.get(client_id)
        assert record is not None
        assert record.next_actions == [ACTION_PACKAGE_AVAILABLE]

        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await resp.get_data())
        assert server_msg.HasField("packages_available")
        record = STORE.get(client_id)
        assert record is not None
        assert record.next_actions is None


@pytest.mark.asyncio
async def test_set_client_actions_rejects_invalid() -> None:
    client_id = "abcd"
    async with app.test_client() as client:
        resp = await client.post(
            f"/api/clients/{client_id}/actions",
            json={"actions": ["not-a-real-action"]},
        )
        assert resp.status_code == 400
