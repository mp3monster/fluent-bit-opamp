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
from opamp_provider.proto import opamp_pb2
from shared.opamp_config import OPAMP_HTTP_PATH


@pytest.mark.asyncio
async def test_package_statuses_returns_error_response() -> None:
    msg = opamp_pb2.AgentToServer(instance_uid=b"\x01\x02")
    msg.package_statuses.SetInParent()

    payload = msg.SerializeToString()
    test_client = app.test_client()
    resp = await test_client.post(
        OPAMP_HTTP_PATH, data=payload, headers={"Content-Type": "application/x-protobuf"}
    )
    body = await resp.get_data()

    reply = opamp_pb2.ServerToAgent()
    reply.ParseFromString(body)

    assert reply.instance_uid == msg.instance_uid
    assert reply.HasField("error_response")
    assert reply.error_response.type != 0
    assert reply.error_response.error_message


@pytest.mark.asyncio
async def test_connection_settings_request_returns_error_response() -> None:
    msg = opamp_pb2.AgentToServer(instance_uid=b"\x03\x04")
    msg.connection_settings_request.opamp.SetInParent()

    payload = msg.SerializeToString()
    test_client = app.test_client()
    resp = await test_client.post(
        OPAMP_HTTP_PATH, data=payload, headers={"Content-Type": "application/x-protobuf"}
    )
    body = await resp.get_data()

    reply = opamp_pb2.ServerToAgent()
    reply.ParseFromString(body)

    assert reply.instance_uid == msg.instance_uid
    assert reply.HasField("error_response")
    assert reply.error_response.type != 0
    assert reply.error_response.error_message
