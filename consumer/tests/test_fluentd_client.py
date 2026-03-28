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

from pathlib import Path

import opamp_consumer.fluentd_client as fluentd_client
from opamp_consumer.client import KEY_SERVICE_TYPE, KEY_SERVICE_VERSION
from opamp_consumer.config import ConsumerConfig


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
    """Fluentd client should parse `fluentd --version` output."""
    instance = fluentd_client.FluentdOpAMPClient("http://localhost", _test_config())
    monkeypatch.setattr(
        fluentd_client.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "fluentd 1.16.7\n",
    )

    instance.add_agent_version(port=24220)

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
    assert loaded.service_instance_id == "fluentd-instance"


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
    monkeypatch.setattr(fluentd_client.subprocess, "Popen", _fake_popen)

    launched = instance.launch_agent_process()

    assert launched is True
    assert captured["command"] == ["fluentd", "-q", "-c", "/tmp/fluentd.conf"]

