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

"""Tests for Fluentd concrete OpAMP consumer implementation."""

from __future__ import annotations

import json
from pathlib import Path

import opamp_consumer.client_mixins as client_mixins
import opamp_consumer.fluentd_client as fluentd_client
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.fluentbit_client import KEY_SERVICE_TYPE, KEY_SERVICE_VERSION
from opamp_consumer.proto import opamp_pb2


def _test_config(agent_config_path: str = "unused") -> ConsumerConfig:
    """Build a minimal test config for Fluentd client tests."""
    return ConsumerConfig(
        server_url="http://localhost",
        agent_config_path=agent_config_path,
        agent_additional_params=[],
        heartbeat_frequency=30,
        log_level="debug",
        service_name="FluentdService",
        service_namespace="FluentdNamespace",
    )


def test_get_agent_description_sets_fluentd_service_type(monkeypatch) -> None:
    """Fluentd client should report service.type as Fluentd."""
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", _test_config())
    instance.data.agent_version = "1.16.0"
    monkeypatch.setattr(instance, "get_host_metadata", lambda: {})

    description = instance.get_agent_description()
    identifying_values = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in description.identifying_attributes
    }

    assert identifying_values[KEY_SERVICE_TYPE] == "Fluentd"
    assert "Fluentd" in identifying_values[KEY_SERVICE_VERSION]


def test_add_agent_version_reads_fluentd_version(monkeypatch) -> None:
    """Fluentd client should read version from monitor_agent API response."""
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", _test_config())

    class FakeResponse:
        """Minimal fake HTTP response for version endpoint tests."""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"version": "1.16.7"}

    captured: dict[str, object] = {}

    def _fake_sleep(delay_seconds: int) -> None:
        captured["delay_seconds"] = delay_seconds

    def _fake_get(url: str, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(fluentd_client.time, "sleep", _fake_sleep)
    monkeypatch.setattr(fluentd_client.httpx, "get", _fake_get)

    instance.add_agent_version(port=24220)

    assert captured["delay_seconds"] == 5
    assert captured["url"] == "http://127.0.0.1:24220/api/config.json"
    assert captured["timeout"] == 5.0
    assert instance.data.agent_version == "1.16.7"
    assert instance.data.agent_type_name == "Fluentd"


def test_load_fluentd_config_parses_monitor_agent_settings(tmp_path: Path) -> None:
    """Fluentd config parser should populate monitor-agent runtime settings."""
    config_path = tmp_path / "fluentd.conf"
    config_path.write_text(
        """
<source>
  @type monitor_agent
  bind 127.0.0.1
  port 24220
</source>
# service_instance_id: fluentd-instance
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = _test_config(agent_config_path=str(config_path))

    loaded = fluentd_client.load_fluentd_config(config)

    assert loaded.client_status_port == 24220
    assert loaded.agent_http_port == 24220
    assert loaded.agent_http_listen == "127.0.0.1"
    assert loaded.agent_http_server == "on"
    assert loaded.server_url == "http://127.0.0.1"
    assert loaded.service_instance_id == "fluentd-instance"


def test_find_monitor_agent_source_bind_and_port_ignores_non_monitor_sources(
    tmp_path: Path,
) -> None:
    """Parser should use bind/port from monitor_agent source only."""
    config_path = tmp_path / "fluentd.conf"
    config_path.write_text(
        """
<source>
  @type forward
  bind 0.0.0.0
  port 24224
</source>
<source>
  @type monitor_agent
  bind 127.0.0.1
  port 24220
</source>
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    bind, port = fluentd_client.find_monitor_agent_source_bind_and_port(config_path)

    assert bind == "127.0.0.1"
    assert port == 24220


def test_load_fluentd_config_does_not_use_non_monitor_agent_port(
    tmp_path: Path,
) -> None:
    """Config loader should not take bind/port values from non-monitor sources."""
    config_path = tmp_path / "fluentd.conf"
    config_path.write_text(
        """
<source>
  @type forward
  bind 0.0.0.0
  port 24224
</source>
<source>
  @type monitor_agent
  bind 127.0.0.1
  port 24220
</source>
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = _test_config(agent_config_path=str(config_path))

    loaded = fluentd_client.load_fluentd_config(config)

    assert loaded.client_status_port == 24220
    assert loaded.agent_http_port == 24220
    assert loaded.agent_http_listen == "127.0.0.1"
    assert loaded.server_url == "http://127.0.0.1"


def test_find_monitor_agent_source_bind_and_port_yaml(
    tmp_path: Path,
) -> None:
    """Parser should extract monitor_agent bind/port from YAML config files."""
    config_path = tmp_path / "fluentd.yaml"
    config_path.write_text(
        """
sources:
  - "@type": forward
    bind: 0.0.0.0
    port: 24224
  - "@type": monitor_agent
    bind: 127.0.0.1
    port: 24220
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    bind, port = fluentd_client.find_monitor_agent_source_bind_and_port(config_path)

    assert bind == "127.0.0.1"
    assert port == 24220


def test_load_fluentd_config_yaml_parses_monitor_agent_settings(
    tmp_path: Path,
) -> None:
    """Config loader should apply monitor_agent bind/port from YAML config."""
    config_path = tmp_path / "fluentd.yaml"
    config_path.write_text(
        """
# service_instance_id: fluentd-yaml-instance
sources:
  - "@type": monitor_agent
    bind: 127.0.0.1
    port: 24220
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = _test_config(agent_config_path=str(config_path))

    loaded = fluentd_client.load_fluentd_config(config)

    assert loaded.client_status_port == 24220
    assert loaded.agent_http_port == 24220
    assert loaded.agent_http_listen == "127.0.0.1"
    assert loaded.agent_http_server == "on"
    assert loaded.server_url == "http://127.0.0.1"
    assert loaded.service_instance_id == "fluentd-yaml-instance"


def test_load_fluentd_config_overrides_server_url_host_with_bind(tmp_path: Path) -> None:
    """Bind value should replace server_url hostname for monitor_agent configs."""
    config_path = tmp_path / "fluentd.conf"
    config_path.write_text(
        """
<source>
  @type monitor_agent
  bind 10.2.3.4
  port 24220
</source>
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = _test_config(agent_config_path=str(config_path))
    config.server_url = "http://localhost:8080/ui?x=1"

    loaded = fluentd_client.load_fluentd_config(config)

    assert loaded.server_url == "http://10.2.3.4:8080/ui?x=1"


def test_load_fluentd_config_port_overrides_client_status_port_from_config(
    tmp_path: Path,
) -> None:
    """Monitor-agent port should override preconfigured client_status_port."""
    config_path = tmp_path / "fluentd.conf"
    config_path.write_text(
        """
<source>
  @type monitor_agent
  bind 127.0.0.1
  port 24220
</source>
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = _test_config(agent_config_path=str(config_path))
    config.client_status_port = 9999

    loaded = fluentd_client.load_fluentd_config(config)

    assert loaded.client_status_port == 24220
    assert loaded.agent_http_port == 24220


def test_load_fluentd_config_yaml_port_overrides_client_status_port_from_config(
    tmp_path: Path,
) -> None:
    """YAML monitor-agent port should override preconfigured client_status_port."""
    config_path = tmp_path / "fluentd.yaml"
    config_path.write_text(
        """
sources:
  - "@type": monitor_agent
    bind: 127.0.0.1
    port: 24220
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = _test_config(agent_config_path=str(config_path))
    config.client_status_port = 9999

    loaded = fluentd_client.load_fluentd_config(config)

    assert loaded.client_status_port == 24220
    assert loaded.agent_http_port == 24220


def test_launch_agent_process_uses_fluentd_command(monkeypatch) -> None:
    """Fluentd client should launch fluentd with config flag and path."""
    captured: dict[str, object] = {}

    class FakeProcess:
        """Minimal fake process object for launch tests."""

        def terminate(self) -> None:
            return None

    def _fake_popen(command: list[str]) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    config = _test_config(agent_config_path="/tmp/fluentd.conf")
    config.agent_additional_params = ["-q"]
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", config)
    monkeypatch.setattr(client_mixins.subprocess, "Popen", _fake_popen)

    launched = instance.launch_agent_process()

    assert launched is True
    assert captured["command"] == ["fluentd", "-q", "-c", "/tmp/fluentd.conf"]


def test_launch_agent_process_returns_false_when_command_not_found(
    monkeypatch,
) -> None:
    """Fluentd launch should fail safely when executable cannot be resolved."""
    config = _test_config(agent_config_path="/tmp/fluentd.conf")
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", config)

    def _raise_not_found(_command: list[str]) -> None:
        raise FileNotFoundError("fluentd")

    monkeypatch.setattr(client_mixins.subprocess, "Popen", _raise_not_found)

    launched = instance.launch_agent_process()

    assert launched is False
    assert instance.data.agent_process is None


def test_add_agent_version_uses_bind_host_for_monitor_agent_api(monkeypatch) -> None:
    """Version lookup should call monitor_agent API using configured bind host."""
    config = _test_config()
    config.agent_http_listen = "10.2.3.4"
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", config)

    class FakeResponse:
        """Minimal fake HTTP response for version endpoint tests."""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"version": "1.16.8"}

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        fluentd_client.time,
        "sleep",
        lambda _seconds: None,
    )

    def _fake_get(url: str, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(fluentd_client.httpx, "get", _fake_get)

    instance.add_agent_version(port=24220)

    assert captured["url"] == "http://10.2.3.4:24220/api/config.json"
    assert captured["timeout"] == 5.0
    assert instance.data.agent_version == "1.16.8"


def test_get_agent_description_sets_fluentd_type_only_after_version_is_known(
    monkeypatch,
) -> None:
    """Service type should remain Fluentd even before version is known."""
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", _test_config())
    monkeypatch.setattr(instance, "get_host_metadata", lambda: {})

    description_before = instance.get_agent_description()
    values_before = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in description_before.identifying_attributes
    }

    instance.data.agent_version = "1.16.9"
    description_after = instance.get_agent_description()
    values_after = {
        item.key: item.value.string_value
        if item.value.WhichOneof("value") == "string_value"
        else ""
        for item in description_after.identifying_attributes
    }

    assert values_before[KEY_SERVICE_TYPE] == "Fluentd"
    assert values_after[KEY_SERVICE_TYPE] == "Fluentd"


def test_poll_local_status_with_codes_uses_plugins_endpoint(monkeypatch) -> None:
    """Heartbeat poll for Fluentd should call monitor_agent /api/plugins.json."""
    config = _test_config()
    config.agent_http_listen = "10.2.3.4"
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", config)

    class FakeResponse:
        """Minimal fake HTTP response for plugins endpoint tests."""

        status_code = 200
        text = '{"plugins":[]}'

        def raise_for_status(self) -> None:
            return None

    captured: dict[str, object] = {}

    def _fake_get(url: str, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(fluentd_client.httpx, "get", _fake_get)

    results, codes = instance.poll_local_status_with_codes(port=24220)

    assert captured["url"] == "http://10.2.3.4:24220/api/plugins.json"
    assert captured["timeout"] == 5.0
    assert results["health"] == '{"plugins":[]}'
    assert codes["health"] == "200"


def test_health_from_metrics_parses_plugins_json_component_health() -> None:
    """Fluentd health parser should map plugins JSON into component health entries."""
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", _test_config())
    message = opamp_pb2.AgentToServer()
    plugins_payload = json.dumps(
        {
            "plugins": [
                {"plugin_id": "in_tail.main", "status": "running", "retry_count": 0},
                {"plugin_id": "out_http.main", "status": "running", "retry_count": 2},
            ]
        }
    )

    updated = instance._health_from_metrics(message, plugins_payload)

    assert updated.health.component_health_map["in_tail.main"].healthy is True
    assert "retry_count=0" in updated.health.component_health_map["in_tail.main"].status
    assert updated.health.component_health_map["out_http.main"].healthy is False
    assert (
        "retry_count=2"
        in updated.health.component_health_map["out_http.main"].status
    )
