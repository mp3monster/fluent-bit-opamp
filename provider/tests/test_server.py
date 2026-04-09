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

import sys

from opamp_provider import config as provider_config
from opamp_provider.config import ProviderConfig, ProviderTLSConfig
from opamp_provider import server as provider_server


def test_server_main_invokes_app(monkeypatch) -> None:
    """Verify server bootstrap by monkeypatching config/app hooks and asserting `main()` forwards parsed host, port, and config."""
    called = {}

    def fake_run(*, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    def fake_load_config_with_overrides(*, config_path, log_level):
        called["log_level_override"] = log_level
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
            log_level="INFO",
        )

    def fake_set_config(config):
        called["config"] = config

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(provider_config, "load_config_with_overrides", fake_load_config_with_overrides)
    monkeypatch.setattr(provider_config, "set_config", fake_set_config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--host", "0.0.0.0", "--port", "9999"],
    )

    provider_server.main()

    assert called["host"] == "0.0.0.0"
    assert called["port"] == 9999
    assert isinstance(called["config"], ProviderConfig)
    assert called["log_level_override"] is None
    assert provider_server.app.config["DIAGNOSTIC_MODE"] is False


def test_server_main_diagnostic_forces_debug_log_level(monkeypatch) -> None:
    """Verify `--diagnostic` forces DEBUG log-level override and enables diagnostic mode."""
    called = {}

    def fake_run(*, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    def fake_load_config_with_overrides(*, config_path, log_level):
        called["log_level_override"] = log_level
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
            log_level=str(log_level or "INFO"),
        )

    def fake_set_config(config):
        called["config"] = config

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(
        provider_config,
        "load_config_with_overrides",
        fake_load_config_with_overrides,
    )
    monkeypatch.setattr(provider_config, "set_config", fake_set_config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--diagnostic", "--log-level", "WARNING"],
    )

    provider_server.main()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8080
    assert isinstance(called["config"], ProviderConfig)
    assert called["log_level_override"] == "DEBUG"
    assert provider_server.app.config["DIAGNOSTIC_MODE"] is True


def test_server_main_passes_tls_cert_and_key_when_configured(monkeypatch) -> None:
    """Verify provider TLS config results in Quart certfile/keyfile run kwargs."""
    called = {}

    def fake_run(*, host: str, port: int, certfile: str | None = None, keyfile: str | None = None) -> None:
        called["host"] = host
        called["port"] = port
        called["certfile"] = certfile
        called["keyfile"] = keyfile

    def fake_load_config_with_overrides(*, config_path, log_level):
        called["log_level_override"] = log_level
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8443,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
            log_level="INFO",
            tls=ProviderTLSConfig(
                cert_file="certs/provider-server.pem",
                key_file="certs/provider-server-key.pem",
                trust_anchor_mode=provider_config.TLS_TRUST_ANCHOR_FULL_CHAIN_TO_ROOT,
            ),
        )

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(
        provider_config,
        "load_config_with_overrides",
        fake_load_config_with_overrides,
    )
    monkeypatch.setattr(provider_config, "set_config", lambda _config: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--host", "0.0.0.0"],
    )

    provider_server.main()

    assert called["host"] == "0.0.0.0"
    assert called["port"] == 8443
    assert called["certfile"] == "certs/provider-server.pem"
    assert called["keyfile"] == "certs/provider-server-key.pem"
