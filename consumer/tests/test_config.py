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
from pathlib import Path

from opamp_consumer import config as consumer_config
from shared.opamp_config import AgentCapabilities


def _base_consumer_config() -> dict:
    return {
        "consumer": {
            "server_url": "http://localhost:4320",
            "transport": "http",
            "log_agent_api_responses": False,
            "agent_config_path": "./fluent-bit.conf",
            "agent_additional_params": [],
            "heartbeat_frequency": 30,
            "log_level": "debug",
            "service_name": "Fluentbit",
            "service_namespace": "FluentBitNS",
        }
    }


def test_allow_custom_capabilities_defaults_false_when_missing(
    tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(_base_consumer_config(), indent=2),
        encoding="utf-8",
    )
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    assert loaded.allow_custom_capabilities is False


def test_allow_custom_capabilities_true_when_configured(
    tmp_path, monkeypatch
) -> None:
    raw = _base_consumer_config()
    raw["consumer"]["allow_custom_capabilities"] = True
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    assert loaded.allow_custom_capabilities is True


def test_chat_ops_port_defaults_none_when_missing(tmp_path, monkeypatch) -> None:
    raw = _base_consumer_config()
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    assert loaded.chat_ops_port is None


def test_chat_ops_port_and_client_status_port_load_when_configured(
    tmp_path, monkeypatch
) -> None:
    raw = _base_consumer_config()
    raw["consumer"]["chat_ops_port"] = 8888
    raw["consumer"]["client_status_port"] = 2020
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    assert loaded.chat_ops_port == 8888
    assert loaded.client_status_port == 2020


def test_agent_capabilities_are_hardwired_and_ignore_config_value(
    tmp_path, monkeypatch
) -> None:
    """Verify agent capabilities are hardwired regardless of config content."""
    raw = _base_consumer_config()
    raw["consumer"]["agent_capabilities"] = ["ReportsHeartbeat"]
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    expected_mask = int(
        AgentCapabilities.ReportsStatus
        | AgentCapabilities.AcceptsRestartCommand
        | AgentCapabilities.ReportsHealth
    )
    assert loaded.agent_capabilities == expected_mask


def test_full_update_controller_loads_from_config_object(tmp_path, monkeypatch) -> None:
    """Load full_update_controller object from config file."""
    raw = _base_consumer_config()
    raw["consumer"]["full_update_controller"] = {"fullResendAfter": 3}
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    assert loaded.full_update_controller == {"fullResendAfter": 3}


def test_full_update_controller_cli_override_uses_string(tmp_path) -> None:
    """Apply full_update_controller CLI override as a JSON string."""
    raw = _base_consumer_config()
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    loaded = consumer_config.load_config_with_overrides(
        config_path=config_path,
        server_url=None,
        server_port=None,
        agent_config_path=None,
        agent_additional_params=None,
        heartbeat_frequency=None,
        log_level=None,
        full_update_controller='{"fullResendAfter":2}',
    )

    assert loaded.full_update_controller == '{"fullResendAfter":2}'


def test_full_update_controller_type_loads_from_config(tmp_path, monkeypatch) -> None:
    """Load full_update_controller_type from config file."""
    raw = _base_consumer_config()
    raw["consumer"]["full_update_controller_type"] = "TimeSend"
    config_path = tmp_path / "opamp.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    monkeypatch.setenv(consumer_config.ENV_OPAMP_CONFIG_PATH, str(config_path))

    loaded = consumer_config.load_config()

    assert loaded.full_update_controller_type == "TimeSend"


def test_fluentd_test_config_loads_successfully() -> None:
    """Ensure the Fluentd test config file is valid for consumer config loading."""
    repo_root = Path(__file__).resolve().parents[2]
    config_path = repo_root / "consumer" / "tests" / "opamp_fluentd.json"

    loaded = consumer_config.load_config_with_overrides(
        config_path=config_path,
        server_url=None,
        server_port=None,
        agent_config_path=None,
        agent_additional_params=None,
        heartbeat_frequency=None,
        log_level=None,
        full_update_controller=None,
    )

    assert loaded.service_name == "Fluentd"
    assert loaded.agent_config_path == "./consumer/tests/fluentd.conf"
