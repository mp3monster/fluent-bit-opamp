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

import opamp_consumer.client_bootstrap as client_bootstrap
import opamp_consumer.fluentbit_client as client
from opamp_consumer.config import ConsumerConfig
from opamp_consumer.fluentbit_client import CONFIG_DOCS_URL


def test_main_help_prints_config_parameters_and_skips_client(
    monkeypatch, capsys
) -> None:
    """`--help` should print config parameters and skip creating OpAMPClient."""
    config = ConsumerConfig(
        server_url="http://localhost",
        agent_config_path="unused",
        agent_additional_params=[],
        heartbeat_frequency=30,
        agent_capabilities=["ReportsStatus"],
        log_level="debug",
    )
    monkeypatch.setattr(
        client.consumer_config, "load_config_with_overrides", lambda **_: config
    )
    monkeypatch.setattr(
        client,
        "OpAMPClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("OpAMPClient should not be created for --help")
        ),
    )
    monkeypatch.setattr(client.sys, "argv", ["fluentbit_client.py", "--help"])

    client.main()

    out = capsys.readouterr().out
    json_start = out.find("{")
    assert json_start >= 0
    payload = json.loads(out[json_start:])
    assert payload["server_url"] == "http://localhost"
    assert payload["documentation_url"] == CONFIG_DOCS_URL


def test_common_parser_accepts_fluentd_aliases() -> None:
    """Shared parser should accept Fluentd-specific argument aliases."""
    parser = client_bootstrap.build_common_cli_parser()

    parsed = parser.parse_args(
        [
            "--config-path",
            "consumer/opamp-fluentd.json",
            "--fluentd-config-path",
            "consumer/fluentd.conf",
            "--additional-fluentd-params",
            "quiet-mode",
        ]
    )

    assert parsed.config_path == "consumer/opamp-fluentd.json"
    assert parsed.agent_config_path == "consumer/fluentd.conf"
    assert parsed.agent_additional_params == ["quiet-mode"]


def test_load_config_from_cli_args_maps_overrides(monkeypatch) -> None:
    """Config loader should map parsed CLI args into override keyword arguments."""
    parser = client_bootstrap.build_common_cli_parser()
    args = parser.parse_args(
        [
            "--config-path",
            "tests/opamp.json",
            "--server-url",
            "http://127.0.0.1",
            "--server-port",
            "8080",
            "--agent-config-path",
            "consumer/fluent-bit.yaml",
            "--agent-additional-params",
            "dry-run",
            "--heartbeat-frequency",
            "15",
            "--log-level",
            "info",
            "--full-update-controller",
            '{"fullResendAfter":10}',
        ]
    )
    captured: dict[str, object] = {}
    expected = ConsumerConfig(
        server_url="http://127.0.0.1",
        agent_config_path="consumer/fluent-bit.yaml",
        agent_additional_params=["--dry-run"],
        heartbeat_frequency=15,
        agent_capabilities=["ReportsStatus"],
        log_level="info",
    )

    monkeypatch.setattr(
        client_bootstrap.consumer_config,
        "get_effective_config_path",
        lambda raw_path: f"/effective/{raw_path}",
    )

    def _fake_load_config_with_overrides(**kwargs) -> ConsumerConfig:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        client_bootstrap.consumer_config,
        "load_config_with_overrides",
        _fake_load_config_with_overrides,
    )

    loaded = client_bootstrap.load_config_from_cli_args(args)

    assert loaded is expected
    assert captured == {
        "config_path": "/effective/tests/opamp.json",
        "server_url": "http://127.0.0.1",
        "server_port": 8080,
        "agent_config_path": "consumer/fluent-bit.yaml",
        "agent_additional_params": ["dry-run"],
        "heartbeat_frequency": 15,
        "log_level": "info",
        "full_update_controller": '{"fullResendAfter":10}',
    }
