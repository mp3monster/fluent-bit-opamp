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

from opamp_provider.app import app
from opamp_provider import config as provider_config
from opamp_provider.config import ProviderConfig
from opamp_provider.proto import opamp_pb2
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
        server_capabilities=1,
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
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
        server_capabilities=1,
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
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
        server_capabilities=1,
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
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
async def test_get_client_missing() -> None:
    async with app.test_client() as client:
        resp = await client.get("/api/clients/missing")
        assert resp.status_code == 404
