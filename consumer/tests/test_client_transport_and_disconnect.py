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

import asyncio
import logging

import httpx
import opamp_consumer.abstract_client as abstract_client
import opamp_consumer.client_mixins as client_mixins
import opamp_consumer.fluentbit_client as client
import pytest
from opamp_consumer.exceptions import AgentException
from opamp_consumer.proto import opamp_pb2


def test_send_as_is_skips_population(monkeypatch) -> None:
    """Send with send_as_is True should skip population."""
    instance = client.OpAMPClient("http://localhost")
    called = {"count": 0}

    def _populate(msg):
        called["count"] += 1
        return msg

    async def _fake_send_http(_msg):
        return None

    monkeypatch.setattr(instance, "_populate_agent_to_server", _populate)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    message = opamp_pb2.AgentToServer()
    asyncio.run(instance.send(message, send_as_is=True))
    assert called["count"] == 0


def test_send_websocket_error_falls_back_to_http(monkeypatch) -> None:
    """WebSocket transport errors should fall back to HTTP send."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.transport = "websocket"
    calls = {"ws": 0, "http": 0}

    async def _fake_send_websocket(_msg):
        calls["ws"] += 1
        raise RuntimeError("ws unavailable")

    async def _fake_send_http(_msg):
        calls["http"] += 1
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(instance, "send_websocket", _fake_send_websocket)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    response = asyncio.run(instance.send(opamp_pb2.AgentToServer(), send_as_is=True))
    assert response is not None
    assert calls == {"ws": 1, "http": 1}


def test_send_returns_none_when_websocket_and_http_fail(monkeypatch, caplog) -> None:
    """Send should return None when both websocket and HTTP paths fail."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.transport = "websocket"
    caplog.set_level(logging.WARNING)

    async def _fake_send_websocket(_msg):
        raise RuntimeError("ws unavailable")

    async def _fake_send_http(_msg):
        raise RuntimeError("http unavailable")

    monkeypatch.setattr(instance, "send_websocket", _fake_send_websocket)
    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    response = asyncio.run(instance.send(opamp_pb2.AgentToServer(), send_as_is=True))
    assert response is None
    assert "Error sending websocket client-to-server message" in caplog.text
    assert "Error sending HTTP client-to-server message" in caplog.text
    assert "transport=websocket" in caplog.text
    assert "transport=http" in caplog.text
    assert "endpoint=http://localhost/v1/opamp" in caplog.text


def test_send_logs_exception_chain_details_for_http_failures(monkeypatch, caplog) -> None:
    """HTTP failure logs should include nested cause details when available."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.transport = "http"
    caplog.set_level(logging.WARNING)

    async def _fake_send_http(_msg):
        raise RuntimeError("All connection attempts failed") from OSError(
            "[Errno 111] Connection refused"
        )

    monkeypatch.setattr(instance, "send_http", _fake_send_http)

    response = asyncio.run(instance.send(opamp_pb2.AgentToServer(), send_as_is=True))

    assert response is None
    assert "Error sending HTTP client-to-server message" in caplog.text
    assert "All connection attempts failed" in caplog.text
    assert "Connection refused" in caplog.text


def test_get_config_value_missing_key_returns_empty_and_logs(caplog) -> None:
    """Missing config keys should return an empty string and log an error."""
    instance = client.OpAMPClient("http://localhost")
    caplog.set_level(logging.ERROR)

    value = instance._get_config_value("not_a_real_config_key")

    assert value == ""
    assert "Error handling request for not_a_real_config_key" in caplog.text


def test_handle_server_to_agent_invalid_reply_returns_false() -> None:
    """Invalid/malformed reply should be handled and return False."""
    instance = client.OpAMPClient("http://localhost")
    reply = opamp_pb2.ServerToAgent()

    assert instance._handle_server_to_agent(reply) is False


def test_populate_disconnect_sets_instance_uid() -> None:
    """Disconnect population should ensure instance UID and agent_disconnect."""
    instance = client.OpAMPClient("http://localhost")
    message = opamp_pb2.AgentToServer()
    instance._populate_disconnect(message)
    assert message.instance_uid == instance.data.uid_instance
    assert message.HasField("agent_disconnect")


def test_terminate_agent_process_terminates_only_launched_process(monkeypatch) -> None:
    """Terminate only the Fluent Bit process launched by the client."""
    instance = client.OpAMPClient("http://localhost")
    called = {"terminate": 0, "wait": 0, "kill": 0}

    class FakeProcess:
        def terminate(self) -> None:
            called["terminate"] += 1

        def wait(self, timeout: float | None = None) -> int:
            called["wait"] += 1
            return 0

        def kill(self) -> None:
            called["kill"] += 1

    monkeypatch.setattr(
        client.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()
    )
    monkeypatch.setattr(
        client_mixins.shutil,
        "which",
        lambda executable: (
            "/usr/bin/fluent-bit"
            if executable == "fluent-bit"
            else None
        ),
    )

    instance.launch_agent_process()
    assert instance.data.agent_process is not None

    instance.terminate_agent_process()
    assert called["terminate"] == 1
    assert called["wait"] == 1
    assert called["kill"] == 0
    assert instance.data.agent_process is None


def test_restart_agent_process_relaunches(monkeypatch) -> None:
    """Restart should terminate existing process and launch a new one."""
    instance = client.OpAMPClient("http://localhost")
    calls = {"terminate": 0, "launch": 0}

    def _terminate() -> None:
        calls["terminate"] += 1

    def _launch() -> bool:
        calls["launch"] += 1
        return True

    monkeypatch.setattr(instance, "terminate_agent_process", _terminate)
    monkeypatch.setattr(instance, "launch_agent_process", _launch)

    assert instance.restart_agent_process() is True
    assert calls["terminate"] == 1
    assert calls["launch"] == 1


def test_restart_agent_process_raises_on_failed_launch(monkeypatch) -> None:
    """Restart should raise AgentException when relaunch fails."""
    instance = client.OpAMPClient("http://localhost")

    monkeypatch.setattr(instance, "terminate_agent_process", lambda: None)
    monkeypatch.setattr(instance, "launch_agent_process", lambda: False)

    with pytest.raises(AgentException):
        instance.restart_agent_process()


def test_send_http_passes_authorization_header_for_env_var_mode(monkeypatch) -> None:
    """HTTP send should attach Authorization header in env-var auth mode."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "env-var"
    monkeypatch.setenv(abstract_client.ENV_OPAMP_TOKEN, "consumer-token")
    captured = {}

    async def _fake_send_http_message(**kwargs):
        captured.update(kwargs)
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(abstract_client, "send_http_message", _fake_send_http_message)

    response = asyncio.run(instance.send_http(opamp_pb2.AgentToServer()))
    assert response is not None
    assert captured["authorization_header"] == "Bearer consumer-token"


def test_send_websocket_passes_authorization_header_for_config_var_mode(
    monkeypatch,
) -> None:
    """WebSocket send should attach Authorization header in config-var auth mode."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "config-var"
    instance.config.opamp_token = "ws-token"
    captured = {}

    async def _fake_send_websocket_message(**kwargs):
        captured.update(kwargs)
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(
        abstract_client,
        "send_websocket_message",
        _fake_send_websocket_message,
    )

    response = asyncio.run(instance.send_websocket(opamp_pb2.AgentToServer()))
    assert response is not None
    assert captured["authorization_header"] == "Bearer ws-token"


def test_authorization_header_is_none_when_mode_none() -> None:
    """Header generation should be skipped when server-authorization is none."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "none"

    assert asyncio.run(instance._resolve_authorization_header_value()) is None
    assert instance.config.server_authorization_header_value is None


def test_authorization_header_env_var_uses_opamp_token(monkeypatch) -> None:
    """Env-var mode should use OpAMP-token environment variable."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "env-var"
    monkeypatch.setenv(abstract_client.ENV_OPAMP_TOKEN, "consumer-token")

    header = asyncio.run(instance._resolve_authorization_header_value())
    assert header == "Bearer consumer-token"


def test_authorization_header_raises_when_env_var_missing(monkeypatch) -> None:
    """Env-var mode should error when no supported env token is configured."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "env-var"
    monkeypatch.delenv(abstract_client.ENV_OPAMP_TOKEN, raising=False)

    with pytest.raises(ValueError, match="server-authorization=env-var"):
        asyncio.run(instance._resolve_authorization_header_value())


def test_idp_mode_requests_token_and_records_header(monkeypatch) -> None:
    """IDP mode should fetch token from IdP and record header name/value on config."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "idp"
    instance.config.idp_token_url = "http://idp.example.com/token"
    instance.config.idp_client_id = "client-id"
    instance.config.idp_client_secret = "client-secret"
    instance.config.idp_scope = "opamp.read"
    instance.config.server_authorization_header_value = None

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"access_token": "idp-token", "token_type": "Bearer"}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data):
            assert url == "http://idp.example.com/token"
            assert data["grant_type"] == "client_credentials"
            assert data["client_id"] == "client-id"
            assert data["client_secret"] == "client-secret"
            assert data["scope"] == "opamp.read"
            return FakeResponse()

    monkeypatch.setattr(abstract_client.httpx, "AsyncClient", FakeAsyncClient)

    header = asyncio.run(instance._resolve_authorization_header_value())
    assert header == "Bearer idp-token"
    assert instance.config.server_authorization_header_name == "Authorization"
    assert instance.config.server_authorization_header_value == "Bearer idp-token"


def test_idp_mode_retries_http_after_auth_error(monkeypatch) -> None:
    """IDP mode should renegotiate credentials and retry once after HTTP 401."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "idp"
    instance.config.server_authorization_header_value = "Bearer old-token"
    calls = {"count": 0, "refresh": 0}

    async def _fake_refresh():
        calls["refresh"] += 1
        instance.config.server_authorization_header_value = "Bearer new-token"
        return "Bearer new-token"

    async def _fake_send_http_message(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            request = httpx.Request("POST", "http://localhost/v1/opamp")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError(
                "unauthorized",
                request=request,
                response=response,
            )
        assert kwargs["authorization_header"] == "Bearer new-token"
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(
        instance,
        "_refresh_idp_authorization_header",
        _fake_refresh,
    )
    monkeypatch.setattr(abstract_client, "send_http_message", _fake_send_http_message)

    response = asyncio.run(instance.send_http(opamp_pb2.AgentToServer()))
    assert response is not None
    assert calls["count"] == 2
    assert calls["refresh"] == 1


def test_idp_mode_retries_websocket_after_auth_error(monkeypatch) -> None:
    """IDP mode should renegotiate credentials and retry once after websocket auth failure."""
    instance = client.OpAMPClient("http://localhost")
    instance.config.server_authorization = "idp"
    instance.config.server_authorization_header_value = "Bearer old-token"
    calls = {"count": 0, "refresh": 0}

    class FakeWebSocketAuthError(Exception):
        status_code = 403

    async def _fake_refresh():
        calls["refresh"] += 1
        instance.config.server_authorization_header_value = "Bearer ws-new-token"
        return "Bearer ws-new-token"

    async def _fake_send_websocket_message(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise FakeWebSocketAuthError("forbidden")
        assert kwargs["authorization_header"] == "Bearer ws-new-token"
        reply = opamp_pb2.ServerToAgent()
        reply.instance_uid = instance.data.uid_instance
        return reply

    monkeypatch.setattr(
        instance,
        "_refresh_idp_authorization_header",
        _fake_refresh,
    )
    monkeypatch.setattr(
        abstract_client,
        "send_websocket_message",
        _fake_send_websocket_message,
    )

    response = asyncio.run(instance.send_websocket(opamp_pb2.AgentToServer()))
    assert response is not None
    assert calls["count"] == 2
    assert calls["refresh"] == 1
