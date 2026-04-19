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

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from opamp_provider import auth as provider_auth
from opamp_provider import config as provider_config
from opamp_provider.app import (
    ACTION_APPLY_CONFIG,
    ACTION_CHANGE_CONNECTIONS,
    ACTION_PACKAGE_AVAILABLE,
    ERR_AGENT_BLOCKED,
    ERR_AGENT_PENDING_APPROVAL,
    _tls_certificate_expiry_metadata,
    app,
)
from opamp_provider.command_implementations.command_shutdown_agent import (
    SHUTDOWN_AGENT_CAPABILITY,
)
from opamp_provider.config import ProviderConfig
from opamp_provider.mcptool.routes import mcp_tool_invoke_custom_command
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import STORE
from opamp_provider.transport import decode_message, encode_message


@pytest.fixture(autouse=True)
def use_temp_opamp_config(tmp_path, monkeypatch) -> pathlib.Path:
    """Run each endpoint test with an isolated writable opamp.json config path."""
    root = pathlib.Path(__file__).resolve().parents[2]
    source = root / "tests" / "opamp.json"
    target = tmp_path / "opamp.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv(provider_config.ENV_OPAMP_CONFIG_PATH, str(target))
    provider_config.set_config(provider_config.load_config())
    yield target


@pytest.fixture(autouse=True)
def reset_store_state() -> None:
    """Reset in-memory store state between endpoint tests."""
    app.config["DIAGNOSTIC_MODE"] = False
    STORE._clients.clear()
    STORE._pending_approvals.clear()
    STORE._blocked_agents.clear()
    STORE._pending_instance_uid_replacements.clear()
    yield
    STORE._clients.clear()
    STORE._pending_approvals.clear()
    STORE._blocked_agents.clear()
    STORE._pending_instance_uid_replacements.clear()
    app.config["DIAGNOSTIC_MODE"] = False


def _test_provider_config(
    *,
    human_in_loop_approval: bool = False,
    opamp_use_authorization: str = provider_config.OPAMP_USE_AUTHORIZATION_NONE,
    ui_use_authorization: str = provider_config.DEFAULT_UI_USE_AUTHORIZATION,
    latest_docs_url: str = provider_config.DEFAULT_LATEST_DOCS_URL,
) -> ProviderConfig:
    """Build a ProviderConfig suitable for endpoint tests."""
    return ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=50,
        log_level="INFO",
        default_heartbeat_frequency=30,
        latest_docs_url=latest_docs_url,
        human_in_loop_approval=human_in_loop_approval,
        opamp_use_authorization=opamp_use_authorization,
        ui_use_authorization=ui_use_authorization,
    )


def _add_agent_description_attribute(
    agent_msg: opamp_pb2.AgentToServer,
    *,
    key: str,
    value: str,
) -> None:
    """Append an identifying string attribute to AgentDescription."""
    item = agent_msg.agent_description.identifying_attributes.add()
    item.key = key
    item.value.string_value = value


def _seed_tool_agent_record(
    *,
    client_id: str,
    disconnected: bool = False,
    remote_addr: str | None = None,
    service_instance_id: str | None = None,
    host_name: str | None = None,
    host_ip: str | None = None,
    client_version: str | None = None,
    custom_capabilities: list[str] | None = None,
    capabilities: int = 0,
) -> None:
    """Insert one tool-visible client record into STORE for /tool/otelAgents tests."""
    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
    agent_msg.sequence_num = 1
    agent_msg.capabilities = capabilities
    if client_version:
        _add_agent_description_attribute(
            agent_msg,
            key="service.version",
            value=client_version,
        )
    if service_instance_id:
        _add_agent_description_attribute(
            agent_msg,
            key="service.instance.id",
            value=service_instance_id,
        )
    if host_name:
        _add_agent_description_attribute(
            agent_msg,
            key="host.name",
            value=host_name,
        )
    if host_ip:
        _add_agent_description_attribute(
            agent_msg,
            key="host.ip",
            value=host_ip,
        )
    if custom_capabilities:
        agent_msg.custom_capabilities.capabilities.extend(custom_capabilities)
    if disconnected:
        agent_msg.agent_disconnect.SetInParent()
    STORE.upsert_from_agent_msg(agent_msg, channel="HTTP", remote_addr=remote_addr)


@pytest.mark.asyncio
async def test_http_endpoint() -> None:
    """Verify `/v1/opamp` HTTP round-trip by posting AgentToServer and asserting instance UID echo."""
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
async def test_http_heartbeat_only_message_skips_autosave_evaluation(monkeypatch) -> None:
    """Verify heartbeat-only OpAMP messages do not trigger autosave interval evaluation."""
    called = {"count": 0}

    def fake_note() -> None:
        called["count"] += 1

    monkeypatch.setattr(
        "opamp_provider.app._note_non_heartbeat_state_change_and_maybe_autosave",
        fake_note,
    )
    agent_msg = opamp_pb2.AgentToServer(
        instance_uid=bytes.fromhex("01010101010101010101010101010101")
    )
    agent_msg.sequence_num = 1

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200

    assert called["count"] == 0


@pytest.mark.asyncio
async def test_http_non_heartbeat_message_runs_autosave_evaluation(monkeypatch) -> None:
    """Verify non-heartbeat OpAMP messages trigger autosave interval evaluation hook."""
    called = {"count": 0}

    def fake_note() -> None:
        called["count"] += 1

    monkeypatch.setattr(
        "opamp_provider.app._note_non_heartbeat_state_change_and_maybe_autosave",
        fake_note,
    )
    agent_msg = opamp_pb2.AgentToServer(
        instance_uid=bytes.fromhex("02020202020202020202020202020202")
    )
    agent_msg.sequence_num = 1
    version = agent_msg.agent_description.identifying_attributes.add()
    version.key = "service.version"
    version.value.string_value = "1.2.3"

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200

    assert called["count"] == 1


@pytest.mark.asyncio
async def test_websocket_endpoint() -> None:
    """Verify `/v1/opamp` WebSocket transport by sending encoded payload and checking decoded response."""
    test_uid = b"abcdef1234567890"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=test_uid)
    agent_msg.capabilities = opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus

    async with app.test_client() as client:
        async with client.websocket("/v1/opamp") as websocket_client:
            await websocket_client.send(encode_message(agent_msg.SerializeToString()))
            data = await websocket_client.receive()

    header, payload = decode_message(data)
    assert header == 0
    server_msg = opamp_pb2.ServerToAgent()
    server_msg.ParseFromString(payload)
    assert server_msg.instance_uid == test_uid


@pytest.mark.asyncio
async def test_human_in_loop_unknown_agent_moves_to_pending_and_rejects_http() -> None:
    """Verify unknown agents are staged for approval and rejected when human-in-loop is enabled."""
    provider_config.set_config(_test_provider_config(human_in_loop_approval=True))
    test_uid = b"1111222233334444"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=test_uid)
    agent_msg.sequence_num = 1

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 403
        pending_resp = await client.get("/api/approvals/pending")
        assert pending_resp.status_code == 200
        pending_payload = await pending_resp.get_json()
        clients_resp = await client.get("/api/clients")
        assert clients_resp.status_code == 200
        clients_payload = await clients_resp.get_json()

    error_msg = opamp_pb2.ServerToAgent()
    error_msg.ParseFromString(await resp.get_data())
    assert error_msg.error_response.error_message == ERR_AGENT_PENDING_APPROVAL
    assert pending_payload["total"] == 1
    assert pending_payload["clients"][0]["client_id"] == test_uid.hex()
    assert clients_payload["total"] == 0
    assert clients_payload["pending_approval_total"] == 1


@pytest.mark.asyncio
async def test_pending_approval_promotes_agent_when_approved() -> None:
    """Verify approval API promotes pending agents into the primary client store."""
    provider_config.set_config(_test_provider_config(human_in_loop_approval=True))
    client_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    initial_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
    initial_msg.sequence_num = 1

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=initial_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 403

        approve_resp = await client.post(
            "/api/approvals/pending",
            json={"decisions": [{"client_id": client_id, "decision": "approve"}]},
        )
        assert approve_resp.status_code == 200
        approve_payload = await approve_resp.get_json()
        assert approve_payload["approved"] == 1
        assert approve_payload["blocked"] == 0
        assert approve_payload["pending_approval_total"] == 0

        follow_up = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
        follow_up.sequence_num = 2
        accepted_resp = await client.post(
            "/v1/opamp",
            data=follow_up.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert accepted_resp.status_code == 200

        listed_resp = await client.get("/api/clients")
        listed_payload = await listed_resp.get_json()

    assert listed_payload["total"] == 1
    assert listed_payload["pending_approval_total"] == 0
    assert listed_payload["clients"][0]["client_id"] == client_id


@pytest.mark.asyncio
async def test_blocked_agent_is_rejected_over_http() -> None:
    """Verify blocked agents are rejected before normal OpAMP processing."""
    provider_config.set_config(_test_provider_config())
    client_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    STORE.block_agent(client_id, reason="unit test block")
    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 403

    error_msg = opamp_pb2.ServerToAgent()
    error_msg.ParseFromString(await resp.get_data())
    assert error_msg.error_response.error_message == ERR_AGENT_BLOCKED


@pytest.mark.asyncio
async def test_human_in_loop_transformation_failure_blocks_agent(monkeypatch) -> None:
    """Verify payload transformation failures while staging approval add the agent to blocked state."""
    provider_config.set_config(_test_provider_config(human_in_loop_approval=True))
    client_id = "cccccccccccccccccccccccccccccccc"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
    agent_msg.sequence_num = 1

    def _raise_pending_failure(*args, **kwargs):
        raise ValueError("transform failed")

    monkeypatch.setattr(STORE, "add_pending_approval_from_agent_msg", _raise_pending_failure)

    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 403

    assert STORE.is_blocked_agent(client_id) is True
    error_msg = opamp_pb2.ServerToAgent()
    error_msg.ParseFromString(await resp.get_data())
    assert error_msg.error_response.error_message == ERR_AGENT_BLOCKED


@pytest.mark.asyncio
async def test_opamp_config_token_rejects_http_without_bearer(monkeypatch) -> None:
    """Verify opamp-use-authorization=config-token rejects missing bearer token."""
    provider_config.set_config(
        _test_provider_config(
            opamp_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_OPAMP_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex("dddd" * 8))
    agent_msg.sequence_num = 1
    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 401

    error_msg = opamp_pb2.ServerToAgent()
    error_msg.ParseFromString(await resp.get_data())
    assert error_msg.error_response.error_message == "missing bearer token"


@pytest.mark.asyncio
async def test_opamp_config_token_accepts_http_with_valid_bearer(monkeypatch) -> None:
    """Verify opamp-use-authorization=config-token accepts valid static bearer."""
    provider_config.set_config(
        _test_provider_config(
            opamp_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_OPAMP_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    test_uid = b"eeeeeeeeeeeeeeee"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=test_uid)
    agent_msg.sequence_num = 1
    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "Authorization": "Bearer local-dev-token",
            },
        )
        assert resp.status_code == 200
        payload = await resp.get_data()

    server_msg = opamp_pb2.ServerToAgent()
    server_msg.ParseFromString(payload)
    assert server_msg.instance_uid == test_uid


@pytest.mark.asyncio
async def test_opamp_idp_rejects_http_without_bearer(monkeypatch) -> None:
    """Verify opamp-use-authorization=idp rejects missing bearer token."""
    provider_config.set_config(
        _test_provider_config(
            opamp_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_IDP
        )
    )
    monkeypatch.setenv(
        provider_auth.ENV_OPAMP_AUTH_JWT_ISSUER, "http://issuer.example.com/realm"
    )
    monkeypatch.setenv(provider_auth.ENV_OPAMP_AUTH_JWT_AUDIENCE, "opamp-ui")
    provider_auth.reload_auth_settings()

    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex("ffff" * 8))
    agent_msg.sequence_num = 1
    async with app.test_client() as client:
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 401

    error_msg = opamp_pb2.ServerToAgent()
    error_msg.ParseFromString(await resp.get_data())
    assert error_msg.error_response.error_message == "missing bearer token"


@pytest.mark.asyncio
async def test_opamp_config_token_rejects_websocket_without_bearer(monkeypatch) -> None:
    """Verify websocket /v1/opamp rejects missing bearer in config-token mode."""
    provider_config.set_config(
        _test_provider_config(
            opamp_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_OPAMP_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    async with app.test_client() as client:
        async with client.websocket("/v1/opamp") as websocket_client:
            data = await websocket_client.receive()

    header, payload = decode_message(data)
    assert header == 0
    server_msg = opamp_pb2.ServerToAgent()
    server_msg.ParseFromString(payload)
    assert server_msg.error_response.error_message == "missing bearer token"


@pytest.mark.asyncio
async def test_opamp_config_token_accepts_websocket_with_valid_bearer(monkeypatch) -> None:
    """Verify websocket /v1/opamp accepts valid bearer in config-token mode."""
    provider_config.set_config(
        _test_provider_config(
            opamp_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_OPAMP_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    test_uid = b"aaaaaaaa11111111"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=test_uid)
    agent_msg.sequence_num = 1

    async with app.test_client() as client:
        async with client.websocket(
            "/v1/opamp",
            headers={"Authorization": "Bearer local-dev-token"},
        ) as websocket_client:
            await websocket_client.send(encode_message(agent_msg.SerializeToString()))
            data = await websocket_client.receive()

    header, payload = decode_message(data)
    assert header == 0
    server_msg = opamp_pb2.ServerToAgent()
    server_msg.ParseFromString(payload)
    assert server_msg.instance_uid == test_uid


@pytest.mark.asyncio
async def test_get_comms_settings(monkeypatch) -> None:
    """Verify GET `/api/settings/comms` returns configured delayed/significant communication thresholds."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)
    monkeypatch.setattr(
        "opamp_provider.app.list_snapshot_files",
        lambda _prefix: [pathlib.Path("a"), pathlib.Path("b")],
    )

    async with app.test_client() as client:
        resp = await client.get("/api/settings/comms")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload == {
        "delayed_comms_seconds": 60,
        "significant_comms_seconds": 300,
        "minutes_keep_disconnected": 30,
        "client_event_history_size": 2,
        "human_in_loop_approval": False,
        "state_persistence_enabled": False,
        "opamp_use_authorization": "none",
        "state_save_folder": "runtime",
        "retention_count": 5,
        "state_snapshot_file_count": 2,
        "autosave_interval_seconds_since_change": 600,
        "tls_enabled": False,
        "https_certificate_expiry_date": None,
        "https_certificate_days_remaining": None,
        "https_certificate_expiring_soon": False,
    }


def test_tls_certificate_expiry_metadata_marks_expiring_soon(monkeypatch) -> None:
    """Verify TLS metadata helper reports certificate expiry and 30-day warning state."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
        tls=provider_config.ProviderTLSConfig(
            cert_file="/tmp/provider-server.pem",
            key_file="/tmp/provider-server-key.pem",
        ),
    )
    provider_config.set_config(config)
    mock_expiry = datetime(2026, 5, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "opamp_provider.app._load_tls_certificate_expiry_utc",
        lambda _cert_file: mock_expiry,
    )

    payload = _tls_certificate_expiry_metadata(
        now_utc=datetime(2026, 4, 8, tzinfo=timezone.utc)
    )

    assert payload == {
        "tls_enabled": True,
        "https_certificate_expiry_date": "2026-05-01",
        "https_certificate_days_remaining": 23,
        "https_certificate_expiring_soon": True,
    }


@pytest.mark.asyncio
async def test_get_diagnostic_settings_disabled_by_default() -> None:
    """Verify diagnostic settings endpoint reports disabled mode by default."""
    async with app.test_client() as client:
        resp = await client.get("/api/settings/diagnostic")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["diagnostic_enabled"] is False
    assert payload["state_persistence_enabled"] is False
    assert isinstance(payload.get("state_persistence"), dict)


@pytest.mark.asyncio
async def test_post_state_save_persists_snapshot_when_enabled(monkeypatch) -> None:
    """Verify manual state-save endpoint triggers snapshot writer when persistence is enabled."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
        state_persistence=provider_config.ProviderStatePersistenceConfig(
            enabled=True,
            state_file_prefix="runtime/opamp_server_state",
        ),
    )
    provider_config.set_config(config)
    captured = {}

    def fake_save_state_snapshot(*, store, persistence, reason, logger=None, now=None):
        captured["reason"] = reason
        captured["state_file_prefix"] = persistence.state_file_prefix
        return pathlib.Path("/tmp/opamp_server_state.20260409T103000Z.json")

    monkeypatch.setattr("opamp_provider.app.save_state_snapshot", fake_save_state_snapshot)

    async with app.test_client() as client:
        resp = await client.post("/api/settings/state/save")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert captured["reason"] == "manual_ui_trigger"
    assert captured["state_file_prefix"] == "runtime/opamp_server_state"
    assert payload["status"] == "saved"
    assert payload["snapshot_path"] == "/tmp/opamp_server_state.20260409T103000Z.json"
    assert isinstance(payload["saved_at_utc"], str)


@pytest.mark.asyncio
async def test_post_state_save_rejects_when_persistence_disabled() -> None:
    """Verify manual state-save endpoint rejects requests when persistence is disabled."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
        state_persistence=provider_config.ProviderStatePersistenceConfig(
            enabled=False,
            state_file_prefix="runtime/opamp_server_state",
        ),
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.post("/api/settings/state/save")
        assert resp.status_code == 400
        payload = await resp.get_json()

    assert payload == {"error": "state persistence is disabled"}


@pytest.mark.asyncio
async def test_get_server_opamp_config_requires_diagnostic_flag() -> None:
    """Verify config diagnostic endpoint is forbidden when diagnostic mode is disabled."""
    app.config["DIAGNOSTIC_MODE"] = False
    async with app.test_client() as client:
        resp = await client.get("/api/settings/server-opamp-config")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_server_opamp_config_returns_config_when_diagnostic_enabled() -> None:
    """Verify config diagnostic endpoint returns config path/text when diagnostic mode is enabled."""
    app.config["DIAGNOSTIC_MODE"] = True
    async with app.test_client() as client:
        resp = await client.get("/api/settings/server-opamp-config")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["diagnostic_enabled"] is True
    assert isinstance(payload.get("config_path"), str)
    assert isinstance(payload.get("config_text"), str)
    loaded = json.loads(payload["config_text"])
    assert isinstance(loaded, dict)
    assert "provider" in loaded


@pytest.mark.asyncio
async def test_put_comms_settings(monkeypatch) -> None:
    """Verify PUT `/api/settings/comms` updates and returns communication threshold settings."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)
    monkeypatch.setattr(
        "opamp_provider.app.list_snapshot_files",
        lambda _prefix: [
            pathlib.Path("a"),
            pathlib.Path("b"),
            pathlib.Path("c"),
        ],
    )

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 120,
                "significant_comms_seconds": 600,
                "minutes_keep_disconnected": 45,
                "client_event_history_size": 4,
                "human_in_loop_approval": True,
                "state_persistence_enabled": True,
                "retention_count": 7,
            },
        )
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload == {
        "delayed_comms_seconds": 120,
        "significant_comms_seconds": 600,
        "minutes_keep_disconnected": 45,
        "client_event_history_size": 4,
        "human_in_loop_approval": True,
        "state_persistence_enabled": True,
        "opamp_use_authorization": "none",
        "state_save_folder": "runtime",
        "retention_count": 7,
        "state_snapshot_file_count": 3,
        "autosave_interval_seconds_since_change": 600,
    }
    config_path = pathlib.Path(provider_config.get_effective_config_path())
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    provider = stored.get("provider", {})
    assert provider.get("delayed_comms_seconds") == 120
    assert provider.get("significant_comms_seconds") == 600
    assert provider.get("minutes_keep_disconnected") == 45
    assert provider.get("client_event_history_size") == 4
    assert provider.get("human_in_loop_approval") is True
    persisted_state_cfg = provider.get("state_persistence", {})
    assert persisted_state_cfg.get("enabled") is True
    assert persisted_state_cfg.get("state_file_prefix") == "runtime/opamp_server_state"
    assert persisted_state_cfg.get("retention_count") == 7
    assert persisted_state_cfg.get("autosave_interval_seconds_since_change") == 600


@pytest.mark.asyncio
async def test_put_comms_settings_creates_timestamped_backup_file() -> None:
    """Verify config persistence creates opamp.json.<date time> backup before overwrite."""
    config_path = pathlib.Path(provider_config.get_effective_config_path())
    original_text = config_path.read_text(encoding="utf-8")

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={"delayed_comms_seconds": 121, "significant_comms_seconds": 601},
        )
        assert resp.status_code == 200

    backups = sorted(config_path.parent.glob(f"{config_path.name}.*"))
    assert backups
    latest_backup = backups[-1]
    assert latest_backup.read_text(encoding="utf-8") == original_text
    assert latest_backup.name.startswith(f"{config_path.name}.")


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid() -> None:
    """Verify PUT `/api/settings/comms` rejects invalid values where delayed exceeds significant."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={"delayed_comms_seconds": 300, "significant_comms_seconds": 60},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid_event_history_size() -> None:
    """Verify PUT `/api/settings/comms` rejects non-positive client event history size values."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 60,
                "significant_comms_seconds": 300,
                "client_event_history_size": 0,
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid_minutes_keep_disconnected() -> None:
    """Verify PUT `/api/settings/comms` rejects non-positive disconnected retention minutes."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 60,
                "significant_comms_seconds": 300,
                "minutes_keep_disconnected": 0,
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid_retention_count() -> None:
    """Verify PUT `/api/settings/comms` rejects non-positive state snapshot retention count values."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 60,
                "significant_comms_seconds": 300,
                "retention_count": 0,
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_comms_settings_triggers_purge_when_retention_below_current_count(
    monkeypatch,
) -> None:
    """Verify lowering retention below current snapshot file count triggers prune."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)
    monkeypatch.setattr(
        "opamp_provider.app.list_snapshot_files",
        lambda _prefix: [
            pathlib.Path("state1"),
            pathlib.Path("state2"),
            pathlib.Path("state3"),
        ],
    )
    captured = {}

    def fake_prune_snapshot_files(*, state_file_prefix: str, retention_count: int, logger=None):
        captured["state_file_prefix"] = state_file_prefix
        captured["retention_count"] = retention_count
        return 2

    monkeypatch.setattr(
        "opamp_provider.app.prune_snapshot_files",
        fake_prune_snapshot_files,
    )

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 60,
                "significant_comms_seconds": 300,
                "retention_count": 1,
            },
        )
        assert resp.status_code == 200

    assert captured["state_file_prefix"] == "runtime/opamp_server_state"
    assert captured["retention_count"] == 1


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid_human_in_loop_approval() -> None:
    """Verify PUT `/api/settings/comms` rejects non-boolean human_in_loop_approval values."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 60,
                "significant_comms_seconds": 300,
                "client_event_history_size": 2,
                "human_in_loop_approval": "maybe",
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_comms_settings_rejects_invalid_state_persistence_enabled() -> None:
    """Verify PUT `/api/settings/comms` rejects non-boolean state_persistence_enabled values."""
    config = ProviderConfig(
        delayed_comms_seconds=60,
        significant_comms_seconds=300,
        webui_port=8080,
        minutes_keep_disconnected=30,
        retry_after_seconds=30,
        client_event_history_size=2,
        log_level="INFO",
    )
    provider_config.set_config(config)

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/comms",
            json={
                "delayed_comms_seconds": 60,
                "significant_comms_seconds": 300,
                "state_persistence_enabled": "maybe",
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_client_settings() -> None:
    """Verify GET `/api/settings/client` returns default heartbeat frequency."""
    STORE.set_default_heartbeat_frequency(30, max_events=50)
    async with app.test_client() as client:
        resp = await client.get("/api/settings/client")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload == {"default_heartbeat_frequency": 30}


@pytest.mark.asyncio
async def test_get_global_settings_help() -> None:
    """Verify global-settings help endpoint returns tooltip text map."""
    async with app.test_client() as client:
        resp = await client.get("/api/help/global-settings")
        assert resp.status_code == 200
        payload = await resp.get_json()

    tooltips = payload.get("tooltips", {})
    fields = payload.get("fields", {})
    assert isinstance(tooltips, dict)
    assert isinstance(fields, dict)
    assert "delayed_comms_seconds" in tooltips
    assert "significant_comms_seconds" in tooltips
    assert "minutes_keep_disconnected" in tooltips
    assert "client_event_history_size" in tooltips
    assert "human_in_loop_approval" in tooltips
    assert "state_persistence_enabled" in tooltips
    assert "state_save_folder" in tooltips
    assert "retention_count" in tooltips
    assert "autosave_interval_seconds_since_change" in tooltips
    assert "default_heartbeat_frequency" in tooltips
    assert fields["delayed_comms_seconds"]["label"] == "Delayed Communications Threshold (seconds)"
    assert fields["significant_comms_seconds"]["label"] == "Significant Communications Threshold (seconds)"
    assert fields["minutes_keep_disconnected"]["label"] == "Disconnected Retention Window (minutes)"
    assert fields["client_event_history_size"]["label"] == "Client Event History Size"
    assert fields["human_in_loop_approval"]["label"] == "Human In Loop Approval"
    assert fields["state_persistence_enabled"]["label"] == "State Persistence Enabled"
    assert fields["state_save_folder"]["label"] == "State Save Folder"
    assert fields["retention_count"]["label"] == "State Snapshot Retention Count"
    assert (
        fields["autosave_interval_seconds_since_change"]["label"]
        == "Autosave Interval Since Change (seconds)"
    )


@pytest.mark.asyncio
async def test_help_page_includes_restore_usage() -> None:
    """Verify `/help` includes restore CLI usage and fallback behavior guidance."""
    async with app.test_client() as client:
        resp = await client.get("/help")
        assert resp.status_code == 200
        html = await resp.get_data(as_text=True)

    assert "--restore" in html
    assert "state_file_prefix" in html
    assert "empty/default in-memory state" in html
    assert "No wildcard characters are needed" in html
    assert "invertFilter=true" in html


@pytest.mark.asyncio
async def test_doc_set_redirect_uses_provider_config_value() -> None:
    """Verify `/doc-set` redirect target is configuration-driven."""
    configured_url = "https://example.org/docs/latest"
    provider_config.set_config(_test_provider_config(latest_docs_url=configured_url))
    async with app.test_client() as client:
        resp = await client.get("/doc-set")
    assert resp.status_code in {301, 302, 307, 308}
    assert resp.headers.get("Location") == configured_url


@pytest.mark.asyncio
async def test_put_client_settings_updates_all_clients_heartbeat_and_events() -> None:
    """Verify PUT `/api/settings/client` updates all clients heartbeat frequency and appends event history entries."""
    STORE._clients.clear()
    STORE.set_default_heartbeat_frequency(30, max_events=50)
    first_client = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
    first_client.sequence_num = 1
    second_client = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"))
    second_client.sequence_num = 1
    record_a = STORE.upsert_from_agent_msg(first_client, channel="HTTP")
    record_b = STORE.upsert_from_agent_msg(second_client, channel="HTTP")
    if record_a.commands:
        record_a.commands[-1].sent_at = record_a.commands[-1].received_at
    if record_b.commands:
        record_b.commands[-1].sent_at = record_b.commands[-1].received_at

    async with app.test_client() as client:
        resp = await client.put(
            "/api/settings/client",
            json={"default_heartbeat_frequency": 45},
        )
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["default_heartbeat_frequency"] == 45
    assert payload["updated_clients"] == 2
    updated_a = STORE.get("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    updated_b = STORE.get("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    assert updated_a is not None
    assert updated_b is not None
    assert updated_a.heartbeat_frequency == 45
    assert updated_b.heartbeat_frequency == 45
    assert updated_a.events[-1].get_event_description() == "send heartbeatfrequency event"
    assert updated_b.events[-1].get_event_description() == "send heartbeatfrequency event"
    config_path = pathlib.Path(provider_config.get_effective_config_path())
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    provider = stored.get("provider", {})
    assert provider.get("default_heartbeat_frequency") == 45


@pytest.mark.asyncio
async def test_set_client_heartbeat_frequency_updates_only_target_client() -> None:
    """Verify per-client heartbeat update only changes the targeted client and appends an event."""
    STORE._clients.clear()
    STORE.set_default_heartbeat_frequency(30, max_events=50)
    first_client = opamp_pb2.AgentToServer(
        instance_uid=bytes.fromhex("cccccccccccccccccccccccccccccccc")
    )
    first_client.sequence_num = 1
    second_client = opamp_pb2.AgentToServer(
        instance_uid=bytes.fromhex("dddddddddddddddddddddddddddddddd")
    )
    second_client.sequence_num = 1
    STORE.upsert_from_agent_msg(first_client, channel="HTTP")
    STORE.upsert_from_agent_msg(second_client, channel="HTTP")

    async with app.test_client() as client:
        resp = await client.put(
            "/api/clients/cccccccccccccccccccccccccccccccc/heartbeat-frequency",
            json={"heartbeat_frequency": 75},
        )
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["client_id"] == "cccccccccccccccccccccccccccccccc"
    assert payload["heartbeat_frequency"] == 75
    updated_a = STORE.get("cccccccccccccccccccccccccccccccc")
    updated_b = STORE.get("dddddddddddddddddddddddddddddddd")
    assert updated_a is not None
    assert updated_b is not None
    assert updated_a.heartbeat_frequency == 75
    assert updated_b.heartbeat_frequency == 30
    assert updated_a.events[-1].get_event_description() == "send heartbeatfrequency event"
    assert all(
        event.get_event_description() != "send heartbeatfrequency event"
        for event in updated_b.events
    )


@pytest.mark.asyncio
async def test_set_client_heartbeat_frequency_unknown_client_returns_404() -> None:
    """Verify per-client heartbeat update returns not found for unknown client IDs."""
    STORE._clients.clear()
    async with app.test_client() as client:
        resp = await client.put(
            "/api/clients/unknown-client/heartbeat-frequency",
            json={"heartbeat_frequency": 45},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_queue_command_requires_payload() -> None:
    """Verify command queue endpoint rejects missing payloads with HTTP 400."""
    async with app.test_client() as client:
        resp = await client.post("/api/clients/client-1/commands")
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_queue_restart_command_and_emit_restart_payload() -> None:
    """Verify restart command queueing creates an event and emits `ServerToAgent.command=Restart` on poll."""
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
        assert event_desc == "Restarts Agent"

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
async def test_queue_force_resync_command_sets_report_full_state_flag() -> None:
    """Verify force-resync queueing emits `ServerToAgent.flags` with `ReportFullState` and marks command sent."""
    client_id = "000000000000000000000000000000ef"
    STORE._clients.clear()

    async with app.test_client() as client:
        queue_resp = await client.post(
            f"/api/clients/{client_id}/commands",
            json=[
                {"key": "classifier", "value": "command"},
                {"key": "action", "value": "forceresync"},
            ],
        )
        assert queue_resp.status_code == 201
        record = STORE.get(client_id)
        assert record is not None
        assert len(record.events) == 1
        assert record.events[0].get_event_description() == "Force Resync"

        agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
        opamp_resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert opamp_resp.status_code == 200
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await opamp_resp.get_data())
        report_full_state = int(
            opamp_pb2.ServerToAgentFlags.ServerToAgentFlags_ReportFullState
        )
        assert server_msg.flags & report_full_state

    record = STORE.get(client_id)
    assert record is not None
    assert len(record.commands) == 1
    assert record.commands[0].sent_at is not None


@pytest.mark.asyncio
async def test_queue_custom_nullcommand_and_emit_custom_message_payload() -> None:
    """Verify custom nullcommand queueing emits `ServerToAgent.custom_message` using dynamic custom-command mapping."""
    client_id = "000000000000000000000000000000aa"
    STORE._clients.clear()

    async with app.test_client() as client:
        queue_resp = await client.post(
            f"/api/clients/{client_id}/commands",
            json=[
                {"key": "classifier", "value": "custom"},
                {"key": "operation", "value": "nullcommand"},
                {"key": "capability", "value": "org.mp3monster.opamp_provider.nullcommand"},
                {"key": "dummyValue", "value": "integration-check"},
            ],
        )
        assert queue_resp.status_code == 201

        agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
        opamp_resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert opamp_resp.status_code == 200
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await opamp_resp.get_data())
        assert server_msg.HasField("custom_message")
        assert (
            server_msg.custom_message.capability
            == "org.mp3monster.opamp_provider.nullcommand"
        )
        assert b'"dummyValue": "integration-check"' in server_msg.custom_message.data


@pytest.mark.asyncio
async def test_queue_command_rejects_unknown_custom_operation() -> None:
    """Verify queue endpoint rejects unknown custom operations even with wildcard custom routing."""
    async with app.test_client() as client:
        resp = await client.post(
            "/api/clients/client-1/commands",
            json=[
                {"key": "classifier", "value": "custom"},
                {"key": "operation", "value": "definitely-not-registered"},
                {"key": "capability", "value": "org.example.custom.unknown"},
            ],
        )
        assert resp.status_code == 400
        payload = await resp.get_json()

    assert payload["error"] == "unsupported custom command mapping"


@pytest.mark.asyncio
async def test_event_history_is_capped_to_configured_size() -> None:
    """Verify command event history is capped by `client_event_history_size` after repeated queue operations."""
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
            log_level="INFO",
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
    """Verify queue endpoint returns HTTP 400 for classifier/action pairs without dispatch mapping."""
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
async def test_tool_otel_agents_returns_only_connected_agents() -> None:
    """Verify `/tool/otelAgents` excludes disconnected clients by seeding one connected and one disconnected."""
    connected_id = "00000000000000000000000000000011"
    disconnected_id = "00000000000000000000000000000022"
    STORE._clients.clear()

    connected_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(connected_id))
    STORE.upsert_from_agent_msg(connected_msg, channel="HTTP")

    disconnected_msg = opamp_pb2.AgentToServer(
        instance_uid=bytes.fromhex(disconnected_id)
    )
    disconnected_msg.agent_disconnect.SetInParent()
    STORE.upsert_from_agent_msg(disconnected_msg, channel="HTTP")

    async with app.test_client() as client:
        resp = await client.get("/tool/otelAgents")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["total"] == 1
    assert len(payload["agents"]) == 1
    assert payload["agents"][0]["client_id"] == connected_id
    assert payload["agents"][0]["disconnected"] is False


@pytest.mark.asyncio
async def test_tool_otel_agents_filter_mdisconnected() -> None:
    """Verify `mdisconnected` toggles connected/disconnected filtering behavior."""
    connected_id = "00000000000000000000000000000033"
    disconnected_id = "00000000000000000000000000000044"
    STORE._clients.clear()
    _seed_tool_agent_record(client_id=connected_id, disconnected=False)
    _seed_tool_agent_record(client_id=disconnected_id, disconnected=True)

    async with app.test_client() as client:
        disconnected_resp = await client.get("/tool/otelAgents?mdisconnected=true")
        connected_resp = await client.get("/tool/otelAgents?mdisconnected=false")
        assert disconnected_resp.status_code == 200
        assert connected_resp.status_code == 200
        disconnected_payload = await disconnected_resp.get_json()
        connected_payload = await connected_resp.get_json()

    assert disconnected_payload["total"] == 1
    assert disconnected_payload["agents"][0]["client_id"] == disconnected_id
    assert disconnected_payload["agents"][0]["disconnected"] is True
    assert connected_payload["total"] == 1
    assert connected_payload["agents"][0]["client_id"] == connected_id
    assert connected_payload["agents"][0]["disconnected"] is False


@pytest.mark.asyncio
async def test_tool_otel_agents_filters_text_fields_and_host_fields() -> None:
    """Verify `/tool/otelAgents` supports text filters for id/version/description/host fields."""
    first_id = "00000000000000000000000000000055"
    second_id = "00000000000000000000000000000066"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        client_version="1.2.3",
        host_name="alpha-node",
        host_ip="10.1.1.5",
        remote_addr="192.168.10.1",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        client_version="9.9.9",
        host_name="beta-node",
        host_ip="10.9.9.9",
        remote_addr="172.20.8.8",
    )

    async with app.test_client() as client:
        by_id_resp = await client.get("/tool/otelAgents?client_id=55")
        by_version_resp = await client.get("/tool/otelAgents?client_version=1.2")
        by_description_resp = await client.get("/tool/otelAgents?agent_description=alpha-node")
        by_host_name_resp = await client.get("/tool/otelAgents?host_name=alpha")
        by_host_ip_resp = await client.get("/tool/otelAgents?host_ip=192.168.10.1")
        assert by_id_resp.status_code == 200
        assert by_version_resp.status_code == 200
        assert by_description_resp.status_code == 200
        assert by_host_name_resp.status_code == 200
        assert by_host_ip_resp.status_code == 200
        by_id_payload = await by_id_resp.get_json()
        by_version_payload = await by_version_resp.get_json()
        by_description_payload = await by_description_resp.get_json()
        by_host_name_payload = await by_host_name_resp.get_json()
        by_host_ip_payload = await by_host_ip_resp.get_json()

    assert by_id_payload["total"] == 1
    assert by_id_payload["agents"][0]["client_id"] == first_id
    assert by_version_payload["total"] == 1
    assert by_version_payload["agents"][0]["client_id"] == first_id
    assert by_description_payload["total"] == 1
    assert by_description_payload["agents"][0]["client_id"] == first_id
    assert by_host_name_payload["total"] == 1
    assert by_host_name_payload["agents"][0]["client_id"] == first_id
    assert by_host_ip_payload["total"] == 1
    assert by_host_ip_payload["agents"][0]["client_id"] == first_id


@pytest.mark.asyncio
async def test_tool_otel_agents_filters_service_instance_id_substring() -> None:
    """Verify `/tool/otelAgents` supports service_instance_id substring filtering."""
    first_id = "00000000000000000000000000000067"
    second_id = "00000000000000000000000000000068"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        service_instance_id="svc-alpha-01",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        service_instance_id="svc-beta-01",
    )

    async with app.test_client() as client:
        by_service_instance_resp = await client.get(
            "/tool/otelAgents?service_instance_id=ha-0"
        )
        assert by_service_instance_resp.status_code == 200
        by_service_instance_payload = await by_service_instance_resp.get_json()

    assert by_service_instance_payload["total"] == 1
    assert by_service_instance_payload["agents"][0]["client_id"] == first_id


@pytest.mark.asyncio
async def test_list_clients_filters_service_instance_version_host_name_and_ip() -> None:
    """Verify `/api/clients` supports query filtering for service ID/version/host/IP."""
    first_id = "00000000000000000000000000000099"
    second_id = "000000000000000000000000000000aa"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        service_instance_id="svc-alpha-01",
        client_version="1.2.3",
        host_name="alpha-node",
        host_ip="10.1.1.5",
        remote_addr="192.168.10.1",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        service_instance_id="svc-beta-01",
        client_version="9.9.9",
        host_name="beta-node",
        host_ip="10.9.9.9",
        remote_addr="172.20.8.8",
    )

    async with app.test_client() as client:
        by_service_instance_resp = await client.get(
            "/api/clients?service_instance_id=ha-0"
        )
        by_version_resp = await client.get("/api/clients?client_version=1.2")
        by_host_name_resp = await client.get("/api/clients?host_name=alpha")
        by_host_ip_resp = await client.get("/api/clients?host_ip=192.168.10.1")
        assert by_service_instance_resp.status_code == 200
        assert by_version_resp.status_code == 200
        assert by_host_name_resp.status_code == 200
        assert by_host_ip_resp.status_code == 200
        by_service_instance_payload = await by_service_instance_resp.get_json()
        by_version_payload = await by_version_resp.get_json()
        by_host_name_payload = await by_host_name_resp.get_json()
        by_host_ip_payload = await by_host_ip_resp.get_json()

    assert by_service_instance_payload["total"] == 1
    assert by_service_instance_payload["clients"][0]["client_id"] == first_id
    assert by_version_payload["total"] == 1
    assert by_version_payload["clients"][0]["client_id"] == first_id
    assert by_host_name_payload["total"] == 1
    assert by_host_name_payload["clients"][0]["client_id"] == first_id
    assert by_host_ip_payload["total"] == 1
    assert by_host_ip_payload["clients"][0]["client_id"] == first_id


@pytest.mark.asyncio
async def test_list_clients_combines_multiple_filters_with_or_semantics() -> None:
    """Verify `/api/clients` combines active text filters with OR semantics."""
    first_id = "000000000000000000000000000000b1"
    second_id = "000000000000000000000000000000b2"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        service_instance_id="svc-alpha-01",
        client_version="1.2.3",
        host_name="alpha-node",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        service_instance_id="svc-beta-01",
        client_version="9.9.9",
        host_name="beta-node",
    )

    async with app.test_client() as client:
        resp = await client.get("/api/clients?host_name=alpha&client_version=9.9")
        assert resp.status_code == 200
        payload = await resp.get_json()

    returned_ids = {item["client_id"] for item in payload["clients"]}
    assert payload["total"] == 2
    assert returned_ids == {first_id, second_id}


@pytest.mark.asyncio
async def test_list_clients_filters_invert_filter_returns_non_matches() -> None:
    """Verify `/api/clients?invertFilter=true` negates active filter matches."""
    first_id = "000000000000000000000000000000c1"
    second_id = "000000000000000000000000000000c2"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        service_instance_id="svc-alpha-01",
        client_version="1.2.3",
        host_name="alpha-node",
        host_ip="10.1.1.5",
        remote_addr="192.168.10.1",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        service_instance_id="svc-beta-01",
        client_version="9.9.9",
        host_name="beta-node",
        host_ip="10.9.9.9",
        remote_addr="172.20.8.8",
    )

    async with app.test_client() as client:
        exclude_resp = await client.get(
            "/api/clients?host_name=alpha&invertFilter=true"
        )
        assert exclude_resp.status_code == 200
        exclude_payload = await exclude_resp.get_json()

    assert exclude_payload["total"] == 1
    assert exclude_payload["clients"][0]["client_id"] == second_id


@pytest.mark.asyncio
async def test_list_clients_invert_filter_with_multiple_filters_uses_or_base() -> None:
    """Verify invertFilter negates OR-based matching across active filters."""
    first_id = "000000000000000000000000000000c4"
    second_id = "000000000000000000000000000000c5"
    third_id = "000000000000000000000000000000c6"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        host_name="alpha-node",
        client_version="1.2.3",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        host_name="beta-node",
        client_version="9.9.9",
    )
    _seed_tool_agent_record(
        client_id=third_id,
        host_name="gamma-node",
        client_version="5.5.5",
    )

    async with app.test_client() as client:
        resp = await client.get(
            "/api/clients?host_name=alpha&client_version=9.9&invertFilter=true"
        )
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["total"] == 1
    assert payload["clients"][0]["client_id"] == third_id


@pytest.mark.asyncio
async def test_list_clients_rejects_invalid_invert_filter_value() -> None:
    """Verify malformed `/api/clients?invertFilter=` values return HTTP 400."""
    _seed_tool_agent_record(client_id="000000000000000000000000000000c3")
    async with app.test_client() as client:
        resp = await client.get("/api/clients?invertFilter=maybe")

    assert resp.status_code == 400
    payload = await resp.get_json()
    assert "invertFilter" in payload["error"]


@pytest.mark.asyncio
async def test_tool_otel_agents_filters_last_communication_range() -> None:
    """Verify communication_since and communication_before filter on last_communication."""
    older_id = "00000000000000000000000000000077"
    newer_id = "00000000000000000000000000000088"
    STORE._clients.clear()
    _seed_tool_agent_record(client_id=older_id)
    _seed_tool_agent_record(client_id=newer_id)

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    older_record = STORE.get(older_id)
    newer_record = STORE.get(newer_id)
    assert older_record is not None
    assert newer_record is not None
    older_record.last_communication = now - timedelta(hours=2)
    newer_record.last_communication = now - timedelta(minutes=10)

    since = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    before = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")

    async with app.test_client() as client:
        since_resp = await client.get(f"/tool/otelAgents?communication_since={since}")
        before_resp = await client.get(f"/tool/otelAgents?communication_before={before}")
        assert since_resp.status_code == 200
        assert before_resp.status_code == 200
        since_payload = await since_resp.get_json()
        before_payload = await before_resp.get_json()

    assert since_payload["total"] == 1
    assert since_payload["agents"][0]["client_id"] == newer_id
    assert before_payload["total"] == 1
    assert before_payload["agents"][0]["client_id"] == older_id


@pytest.mark.asyncio
async def test_tool_otel_agents_filters_supports_command_name() -> None:
    """Verify supports_command_name filters by inferred standard/custom command support."""
    restart_id = "00000000000000000000000000000099"
    custom_id = "000000000000000000000000000000aa"
    none_id = "000000000000000000000000000000bb"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=restart_id,
        capabilities=opamp_pb2.AgentCapabilities.AgentCapabilities_AcceptsRestartCommand,
    )
    _seed_tool_agent_record(
        client_id=custom_id,
        custom_capabilities=[SHUTDOWN_AGENT_CAPABILITY],
    )
    _seed_tool_agent_record(client_id=none_id)

    async with app.test_client() as client:
        restart_resp = await client.get("/tool/otelAgents?supports_command_name=restart")
        shutdown_resp = await client.get("/tool/otelAgents?supports_command_name=shutdown")
        assert restart_resp.status_code == 200
        assert shutdown_resp.status_code == 200
        restart_payload = await restart_resp.get_json()
        shutdown_payload = await shutdown_resp.get_json()

    assert restart_payload["total"] == 1
    assert restart_payload["agents"][0]["client_id"] == restart_id
    assert shutdown_payload["total"] == 1
    assert shutdown_payload["agents"][0]["client_id"] == custom_id


@pytest.mark.asyncio
async def test_tool_otel_agents_rejects_invalid_filter_values() -> None:
    """Verify invalid bool/datetime filter values produce HTTP 400 error payloads."""
    _seed_tool_agent_record(client_id="000000000000000000000000000000cc")
    async with app.test_client() as client:
        invalid_date = await client.get("/tool/otelAgents?communication_since=not-a-date")
        invalid_bool = await client.get("/tool/otelAgents?mdisconnected=maybe")

    assert invalid_date.status_code == 400
    invalid_date_payload = await invalid_date.get_json()
    assert "communication_since" in invalid_date_payload["error"]
    assert invalid_bool.status_code == 400
    invalid_bool_payload = await invalid_bool.get_json()
    assert "mdisconnected" in invalid_bool_payload["error"]


@pytest.mark.asyncio
async def test_tool_otel_agents_invert_filter_returns_non_matches() -> None:
    """Verify `/tool/otelAgents?invertFilter=true` negates active filter matches."""
    first_id = "000000000000000000000000000000d1"
    second_id = "000000000000000000000000000000d2"
    STORE._clients.clear()
    _seed_tool_agent_record(
        client_id=first_id,
        host_name="alpha-node",
    )
    _seed_tool_agent_record(
        client_id=second_id,
        host_name="beta-node",
    )

    async with app.test_client() as client:
        exclude_resp = await client.get(
            "/tool/otelAgents?host_name=alpha&invertFilter=true"
        )
        assert exclude_resp.status_code == 200
        exclude_payload = await exclude_resp.get_json()

    assert exclude_payload["total"] == 1
    assert exclude_payload["agents"][0]["client_id"] == second_id


@pytest.mark.asyncio
async def test_tool_openapi_spec_lists_tool_endpoints() -> None:
    """Verify `/tool` serves OpenAPI metadata that includes documented tool endpoint paths."""
    async with app.test_client() as client:
        resp = await client.get("/tool")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["openapi"] == "3.0.3"
    assert payload["info"]["title"] == "OpAMP Provider Tool API"
    paths = payload.get("paths", {})
    assert "/tool" in paths
    assert "/tool/otelAgents" in paths
    assert "/tool/commands" in paths
    assert "get" in paths["/tool/commands"]
    assert "responses" in paths["/tool/commands"]["get"]
    otel_agents_get = paths["/tool/otelAgents"]["get"]
    param_names = {
        param.get("name")
        for param in otel_agents_get.get("parameters", [])
        if isinstance(param, dict)
    }
    assert "agent_description" in param_names
    assert "client_id" in param_names
    assert "communication_before" in param_names
    assert "communication_since" in param_names
    assert "client_version" in param_names
    assert "mdisconnected" in param_names
    assert "supports_command_name" in param_names
    assert "service_instance_id" in param_names
    assert "host_name" in param_names
    assert "host_ip" in param_names
    assert "invertFilter" in param_names


@pytest.mark.asyncio
async def test_tool_auth_static_mode_rejects_missing_bearer_token(monkeypatch) -> None:
    """Verify static auth mode rejects unauthenticated `/tool` requests with HTTP 401."""
    provider_config.set_config(
        _test_provider_config(
            ui_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_UI_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    async with app.test_client() as client:
        resp = await client.get("/tool")
        assert resp.status_code == 401
        payload = await resp.get_json()

    assert payload == {"error": "missing bearer token"}
    assert (
        resp.headers.get("WWW-Authenticate") == provider_auth.WWW_AUTHENTICATE_BEARER
    )


@pytest.mark.asyncio
async def test_ui_requires_bearer_token_when_ui_idp_mode_and_missing_bearer(
    monkeypatch,
) -> None:
    """Verify browser UI paths reject missing bearer token when ui-use-authorization=idp."""
    provider_config.set_config(
        _test_provider_config(
            ui_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_IDP
        )
    )
    monkeypatch.setenv(
        provider_auth.ENV_UI_AUTH_JWT_ISSUER, "http://127.0.0.1:8081/realms/opamp"
    )
    monkeypatch.setenv(provider_auth.ENV_UI_AUTH_JWT_AUDIENCE, "opamp-ui")
    provider_auth.reload_auth_settings()

    async with app.test_client() as client:
        resp = await client.get("/ui")

    assert resp.status_code == 401
    payload = await resp.get_json()
    assert payload == {"error": "missing bearer token"}


@pytest.mark.asyncio
async def test_web_ui_references_external_javascript_bundle(monkeypatch) -> None:
    """Verify `/ui` references external UI assets and each one is served."""
    provider_config.set_config(
        _test_provider_config(
            ui_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_NONE
        )
    )
    provider_auth.reload_auth_settings()

    async with app.test_client() as client:
        ui_resp = await client.get("/ui")
        assert ui_resp.status_code == 200
        ui_html = (await ui_resp.get_data()).decode("utf-8")
        assert '<link rel="stylesheet" href="/web_ui.css" />' in ui_html
        assert '<script src="/web_ui_state.js"></script>' in ui_html
        assert '<script src="/web_ui_functions.js"></script>' in ui_html
        assert '<script src="/web_ui_bindings.js"></script>' in ui_html

        css_resp = await client.get("/web_ui.css")
        assert css_resp.status_code == 200
        assert css_resp.headers.get("Content-Type", "").startswith("text/css")
        css_text = (await css_resp.get_data()).decode("utf-8")

        state_js_resp = await client.get("/web_ui_state.js")
        assert state_js_resp.status_code == 200
        assert (
            state_js_resp.headers.get("Content-Type", "").startswith(
                "application/javascript"
            )
        )
        state_js_text = (await state_js_resp.get_data()).decode("utf-8")

        functions_js_resp = await client.get("/web_ui_functions.js")
        assert functions_js_resp.status_code == 200
        assert (
            functions_js_resp.headers.get("Content-Type", "").startswith(
                "application/javascript"
            )
        )
        functions_js_text = (await functions_js_resp.get_data()).decode("utf-8")

        bindings_js_resp = await client.get("/web_ui_bindings.js")
        assert bindings_js_resp.status_code == 200
        assert (
            bindings_js_resp.headers.get("Content-Type", "").startswith(
                "application/javascript"
            )
        )
        bindings_js_text = (await bindings_js_resp.get_data()).decode("utf-8")

    assert ":root {" in css_text
    assert "const state = {" in state_js_text
    assert "async function fetchClients()" in functions_js_text
    assert "init();" in bindings_js_text


@pytest.mark.asyncio
async def test_tool_auth_static_mode_accepts_valid_bearer_token(monkeypatch) -> None:
    """Verify static auth mode accepts `/tool` requests when the bearer token matches."""
    provider_config.set_config(
        _test_provider_config(
            ui_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_UI_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    async with app.test_client() as client:
        resp = await client.get(
            "/tool",
            headers={"Authorization": "Bearer local-dev-token"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_auth_static_mode_protects_ui_api_routes(monkeypatch) -> None:
    """Verify static auth mode protects `/api/*` endpoints by default."""
    provider_config.set_config(
        _test_provider_config(
            ui_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_UI_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()

    async with app.test_client() as client:
        unauthorized = await client.get("/api/clients")
        authorized = await client.get(
            "/api/clients",
            headers={"Authorization": "Bearer local-dev-token"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


@pytest.mark.asyncio
async def test_tool_auth_static_mode_logs_rejection_details(monkeypatch, caplog) -> None:
    """Verify token mismatches are rejected and written to logs for operator visibility."""
    provider_config.set_config(
        _test_provider_config(
            ui_use_authorization=provider_config.OPAMP_USE_AUTHORIZATION_CONFIG_TOKEN
        )
    )
    monkeypatch.setenv(provider_auth.ENV_UI_AUTH_STATIC_TOKEN, "local-dev-token")
    provider_auth.reload_auth_settings()
    caplog.set_level("WARNING")

    async with app.test_client() as client:
        resp = await client.get(
            "/tool/commands",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    assert "authorization rejected" in caplog.text
    assert "static token mismatch" in caplog.text


@pytest.mark.asyncio
async def test_tool_commands_returns_standard_and_custom_commands() -> None:
    """Verify `/tool/commands` returns both standard and custom command metadata entries."""
    async with app.test_client() as client:
        resp = await client.get("/tool/commands")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert "commands" in payload
    commands = payload["commands"]
    assert isinstance(commands, list)
    assert payload["total"] == len(commands)
    assert commands

    classifiers = {entry.get("classifier") for entry in commands}
    assert "command" in classifiers
    assert "custom" in classifiers

    operations = {entry.get("operation") for entry in commands}
    assert "restart" in operations
    assert "chatopcommand" in operations


def test_mcp_tool_invoke_custom_command_queues_valid_custom_command() -> None:
    """Verify MCP custom-command tool queues valid command payloads for a client."""
    client_id = "0000000000000000000000000000005a"
    result = mcp_tool_invoke_custom_command(
        client_id=client_id,
        operation="nullcommand",
        capability="org.mp3monster.opamp_provider.nullcommand",
        parameters={"dummyValue": "queued-via-mcp"},
    )

    assert result["status"] == "queued"
    assert result["client_id"] == client_id
    assert result["classifier"] == "custom"
    assert result["action"] == "nullcommand"

    record = STORE.get(client_id)
    assert record is not None
    assert len(record.commands) == 1
    queued = record.commands[0]
    assert queued.classifier == "custom"
    assert queued.action == "nullcommand"
    pairs = {entry["key"]: entry["value"] for entry in queued.key_value_pairs}
    assert pairs["dummyValue"] == "queued-via-mcp"


def test_mcp_tool_invoke_custom_command_returns_friendly_error_for_unknown_command() -> None:
    """Verify MCP custom-command tool returns friendly validation details for unknown operations."""
    client_id = "0000000000000000000000000000005b"
    result = mcp_tool_invoke_custom_command(
        client_id=client_id,
        operation="definitely-not-registered",
        capability="org.example.custom.unknown",
        parameters={"dummyValue": "not-used"},
    )

    assert result["status"] == "error"
    assert result["status_code"] == 400
    assert result["error"].startswith("Custom command request rejected:")
    assert result["validation_error"]["error"] == "unsupported custom command mapping"

    record = STORE.get(client_id)
    assert record is None or len(record.commands) == 0


def test_mcp_tool_invoke_custom_command_rejects_invalid_payload_shape() -> None:
    """Verify MCP custom-command tool validates reserved keys and non-primitive parameter values."""
    client_id = "0000000000000000000000000000005c"

    reserved_result = mcp_tool_invoke_custom_command(
        client_id=client_id,
        operation="nullcommand",
        capability="org.mp3monster.opamp_provider.nullcommand",
        parameters={"classifier": "command"},
    )
    assert reserved_result["status"] == "error"
    assert reserved_result["status_code"] == 400
    assert reserved_result["error"].startswith("Custom command request rejected:")
    assert "reserved" in reserved_result["validation_error"]["error"]

    nonprimitive_result = mcp_tool_invoke_custom_command(
        client_id=client_id,
        operation="nullcommand",
        capability="org.mp3monster.opamp_provider.nullcommand",
        parameters={"dummyValue": {"nested": "object-not-allowed"}},
    )
    assert nonprimitive_result["status"] == "error"
    assert nonprimitive_result["status_code"] == 400
    assert nonprimitive_result["error"].startswith("Custom command request rejected:")
    assert "must be a primitive value" in nonprimitive_result["validation_error"]["error"]

    record = STORE.get(client_id)
    assert record is None or len(record.commands) == 0


@pytest.mark.asyncio
async def test_list_custom_commands_returns_display_names_and_schema() -> None:
    """Verify `/api/commands/custom` includes expected custom command metadata and sanitized schema rows."""
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
    assert (
        first["description"]
        == "Uses the chat ops strategy to provide a dynamic means to get the agent to perform a task based on its existing configuration."
    )
    assert first["classifier"] == "custom"
    assert first["operation"] == "chatopcommand"
    assert first["reported_by_client"] is False
    assert isinstance(first["schema"], list)
    assert {
        "parametername": "tag",
        "type": "string",
        "description": "Custom command operation name.",
        "isrequired": True,
    } in first["schema"]
    for row in first["schema"]:
        assert row.get("parametername") not in {"classifier", "type", "data"}
    shutdown = command_map["shutdownagent"]
    assert shutdown["fqdn"] == "org.mp3monster.opamp_provider.command_shutdown_agent"
    assert shutdown["displayname"] == "Shutdown Agent"
    assert shutdown["description"] == "Instruction for telling an agent to shutdown"
    assert shutdown["schema"] == []
    nullcommand = command_map["nullcommand"]
    assert nullcommand["fqdn"] == "org.mp3monster.opamp_provider.nullcommand"
    assert nullcommand["displayname"] == "Null Command"
    assert (
        nullcommand["description"]
        == "Null command provides a means to check the custom command configuration without impact"
    )
    assert nullcommand["reported_by_client"] is False
    assert nullcommand["schema"] == [
        {
            "parametername": "dummyValue",
            "type": "string",
            "description": "Dummy value used for nullcommand log output on the consumer.",
            "isrequired": False,
        },
    ]


@pytest.mark.asyncio
async def test_list_custom_commands_marks_reported_capabilities_for_client() -> None:
    """Verify custom command list marks capabilities reported by a specific client via `reported_by_client`."""
    client_id = "00000000000000000000000000000033"
    STORE._clients.clear()
    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
    agent_msg.custom_capabilities.capabilities.extend(
        ["org.mp3monster.opamp_provider.chatopcommand"]
    )
    STORE.upsert_from_agent_msg(agent_msg, channel="HTTP")

    async with app.test_client() as client:
        resp = await client.get(f"/api/commands/custom?client_id={client_id}")
        assert resp.status_code == 200
        payload = await resp.get_json()

    command_map = {entry["operation"]: entry for entry in payload["commands"]}
    assert command_map["chatopcommand"]["reported_by_client"] is True
    assert command_map["shutdownagent"]["reported_by_client"] is False


@pytest.mark.asyncio
async def test_get_client_missing() -> None:
    """Verify GET `/api/clients/<id>` returns 404 when the requested client record does not exist."""
    async with app.test_client() as client:
        resp = await client.get("/api/clients/missing")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_issue_identification_rekeys_client_to_new_instance_uid() -> None:
    """Verify issuing a new unique ID migrates provider state to the replacement client ID."""
    STORE._clients.clear()
    old_client_id = "11111111111111111111111111111111"

    async with app.test_client() as client:
        first = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(old_client_id))
        first.sequence_num = 1
        version = first.agent_description.identifying_attributes.add()
        version.key = "service.version"
        version.value.string_value = "4.2.0"
        resp = await client.post(
            "/v1/opamp",
            data=first.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200

        identify_resp = await client.post(f"/api/clients/{old_client_id}/identify")
        assert identify_resp.status_code == 200
        identify_payload = await identify_resp.get_json()
        new_client_id = identify_payload["new_instance_uid"]
        identify_record = STORE.get(old_client_id)
        assert identify_record is not None
        assert identify_record.events[-1].get_event_description() == "Issue New Unique ID"

        second = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(old_client_id))
        second.sequence_num = 2
        resp = await client.post(
            "/v1/opamp",
            data=second.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await resp.get_data())
        assert server_msg.agent_identification.new_instance_uid.hex() == new_client_id

        third = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(new_client_id))
        third.sequence_num = 3
        resp = await client.post(
            "/v1/opamp",
            data=third.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200

        list_resp = await client.get("/api/clients")
        assert list_resp.status_code == 200
        listed = await list_resp.get_json()

    assert listed["total"] == 1
    assert listed["clients"][0]["client_id"] == new_client_id
    assert listed["clients"][0]["client_version"] == "4.2.0"
    assert listed["clients"][0]["events"][-1]["event_description"] == "Issue New Unique ID"


@pytest.mark.asyncio
async def test_list_clients_serializes_pending_identification_bytes() -> None:
    """Verify GET `/api/clients` handles non-UTF8 pending instance UID bytes by returning hex."""
    STORE._clients.clear()
    client_id = "11111111111111111111111111111111"
    agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
    record = STORE.upsert_from_agent_msg(agent_msg, channel="HTTP")
    record.pending_agent_identification = b"\x01\x9d"

    async with app.test_client() as client:
        resp = await client.get("/api/clients")
        assert resp.status_code == 200
        payload = await resp.get_json()

    assert payload["total"] == 1
    assert payload["clients"][0]["client_id"] == client_id
    assert payload["clients"][0]["pending_agent_identification"] == "019d"


@pytest.mark.asyncio
async def test_set_client_actions_and_http_consumes() -> None:
    """Verify queued next-actions are consumed in order across successive HTTP OpAMP polls."""
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
        assert server_msg.HasField("error_response")
        assert (
            server_msg.error_response.error_message
            == "Package Availability feature not available"
        )
        record = STORE.get(client_id)
        assert record is not None
        assert record.next_actions is None


@pytest.mark.asyncio
async def test_change_connections_sets_opamp_heartbeat_interval_from_client_record() -> None:
    """Verify change-connections action emits OpAMP connection settings heartbeat interval from the client record."""
    client_id = "5678"
    STORE._clients.clear()

    initial_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
    initial_msg.sequence_num = 1
    record = STORE.upsert_from_agent_msg(initial_msg, channel="HTTP")
    if record.commands:
        record.commands[-1].sent_at = record.commands[-1].received_at
    record.heartbeat_frequency = 42

    async with app.test_client() as client:
        resp = await client.post(
            f"/api/clients/{client_id}/actions",
            json={"actions": [ACTION_CHANGE_CONNECTIONS]},
        )
        assert resp.status_code == 200

        agent_msg = opamp_pb2.AgentToServer(instance_uid=bytes.fromhex(client_id))
        agent_msg.sequence_num = 2
        resp = await client.post(
            "/v1/opamp",
            data=agent_msg.SerializeToString(),
            headers={"Content-Type": "application/x-protobuf"},
        )
        assert resp.status_code == 200
        server_msg = opamp_pb2.ServerToAgent()
        server_msg.ParseFromString(await resp.get_data())
        assert server_msg.HasField("connection_settings")
        assert server_msg.connection_settings.opamp.heartbeat_interval_seconds == 42

    record = STORE.get(client_id)
    assert record is not None
    assert record.next_actions is None


@pytest.mark.asyncio
async def test_set_client_actions_rejects_invalid() -> None:
    """Verify invalid next-action values are rejected with HTTP 400 by `/api/clients/<id>/actions`."""
    client_id = "abcd"
    async with app.test_client() as client:
        resp = await client.post(
            f"/api/clients/{client_id}/actions",
            json={"actions": ["not-a-real-action"]},
        )
        assert resp.status_code == 400
