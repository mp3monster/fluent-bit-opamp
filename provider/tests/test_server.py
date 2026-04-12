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

import logging
import pathlib
import sys

from opamp_provider import config as provider_config
from opamp_provider import server as provider_server
from opamp_provider.config import ProviderConfig, ProviderTLSConfig


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


def test_server_main_restore_missing_snapshot_sets_missing_status(monkeypatch, caplog) -> None:
    """Verify `--restore` missing snapshot path records restore status and still starts app."""
    called = {}
    caplog.set_level(logging.INFO)

    def fake_run(*, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    def fake_load_config_with_overrides(*, config_path, log_level):
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
            log_level="INFO",
            state_persistence=provider_config.ProviderStatePersistenceConfig(
                enabled=True,
                state_file_prefix="runtime/opamp_server_state",
            ),
        )

    statuses = []

    def fake_set_restore_status(status: str, detail: str = "") -> None:
        statuses.append((status, detail))

    def fake_resolve_restore_snapshot_path(*, state_file_prefix: str, restore_option: str):
        raise FileNotFoundError("missing snapshot")

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(
        provider_config,
        "load_config_with_overrides",
        fake_load_config_with_overrides,
    )
    monkeypatch.setattr(provider_config, "set_config", lambda _config: None)
    monkeypatch.setattr(provider_server, "set_state_restore_status", fake_set_restore_status)
    monkeypatch.setattr(
        provider_server,
        "resolve_restore_snapshot_path",
        fake_resolve_restore_snapshot_path,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--restore"],
    )

    provider_server.main()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8080
    assert statuses
    assert statuses[-1][0] == "missing"
    assert "restore requested but snapshot missing" in caplog.text
    assert (
        "state restore fallback: no snapshot file available, starting with empty in-memory state"
        in caplog.text
    )


def test_server_main_restore_explicit_snapshot_path_uses_argument(monkeypatch, caplog) -> None:
    """Verify `--restore <path>` uses explicit snapshot path and restores before app.run."""
    called = {"order": []}
    explicit_snapshot = "/tmp/opamp_server_state.20260409T103000Z.json"
    caplog.set_level(logging.INFO)

    def fake_run(*, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port
        called["order"].append("run")

    def fake_load_config_with_overrides(*, config_path, log_level):
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
            log_level="INFO",
            state_persistence=provider_config.ProviderStatePersistenceConfig(
                enabled=True,
                state_file_prefix="runtime/opamp_server_state",
            ),
        )

    statuses = []
    resolved = {}

    def fake_set_restore_status(status: str, detail: str = "") -> None:
        statuses.append((status, detail))

    def fake_resolve_restore_snapshot_path(*, state_file_prefix: str, restore_option: str):
        resolved["state_file_prefix"] = state_file_prefix
        resolved["restore_option"] = restore_option
        return pathlib.Path(explicit_snapshot)

    def fake_restore_state_snapshot(*, store, snapshot_path, logger=None):
        called["order"].append("restore")
        called["snapshot_path"] = str(snapshot_path)
        return {
            "clients": 0,
            "pending_approvals": 0,
            "blocked_agents": 0,
            "pending_instance_uid_replacements": 0,
            "full_refresh_queued": 0,
            "unknown_attributes_ignored": 0,
        }

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(
        provider_config,
        "load_config_with_overrides",
        fake_load_config_with_overrides,
    )
    monkeypatch.setattr(provider_config, "set_config", lambda _config: None)
    monkeypatch.setattr(provider_server, "set_state_restore_status", fake_set_restore_status)
    monkeypatch.setattr(
        provider_server,
        "resolve_restore_snapshot_path",
        fake_resolve_restore_snapshot_path,
    )
    monkeypatch.setattr(
        provider_server,
        "restore_state_snapshot",
        fake_restore_state_snapshot,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--restore", explicit_snapshot],
    )

    provider_server.main()

    assert resolved["state_file_prefix"] == "runtime/opamp_server_state"
    assert resolved["restore_option"] == explicit_snapshot
    assert called["snapshot_path"] == explicit_snapshot
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8080
    assert called["order"] == ["restore", "run"]
    assert statuses
    assert statuses[-1][0] == "restored"
    assert f"state restore using snapshot file: {explicit_snapshot}" in caplog.text


def test_server_main_restore_invalid_snapshot_sets_failed_status(monkeypatch) -> None:
    """Verify invalid restore content marks restore as failed and provider still starts."""
    called = {}

    def fake_run(*, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    def fake_load_config_with_overrides(*, config_path, log_level):
        return ProviderConfig(
            delayed_comms_seconds=60,
            significant_comms_seconds=300,
            webui_port=8080,
            minutes_keep_disconnected=30,
            retry_after_seconds=30,
            client_event_history_size=50,
            log_level="INFO",
            state_persistence=provider_config.ProviderStatePersistenceConfig(
                enabled=True,
                state_file_prefix="runtime/opamp_server_state",
            ),
        )

    statuses = []

    def fake_set_restore_status(status: str, detail: str = "") -> None:
        statuses.append((status, detail))

    def fake_resolve_restore_snapshot_path(*, state_file_prefix: str, restore_option: str):
        return pathlib.Path("/tmp/opamp_server_state.20260409T103000Z.json")

    def fake_restore_state_snapshot(*, store, snapshot_path, logger=None):
        raise ValueError("invalid snapshot payload")

    monkeypatch.setattr(provider_server.app, "run", fake_run)
    monkeypatch.setattr(
        provider_config,
        "load_config_with_overrides",
        fake_load_config_with_overrides,
    )
    monkeypatch.setattr(provider_config, "set_config", lambda _config: None)
    monkeypatch.setattr(provider_server, "set_state_restore_status", fake_set_restore_status)
    monkeypatch.setattr(
        provider_server,
        "resolve_restore_snapshot_path",
        fake_resolve_restore_snapshot_path,
    )
    monkeypatch.setattr(
        provider_server,
        "restore_state_snapshot",
        fake_restore_state_snapshot,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--restore"],
    )

    provider_server.main()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8080
    assert statuses
    assert statuses[-1][0] == "failed"


def test_server_main_logs_warning_when_provider_config_load_fails(monkeypatch, caplog) -> None:
    """Verify provider config load failures are logged as warnings."""
    caplog.set_level(logging.WARNING)

    def fake_load_config_with_overrides(*, config_path, log_level):
        raise ValueError("bad provider config")

    monkeypatch.setattr(
        provider_config,
        "load_config_with_overrides",
        fake_load_config_with_overrides,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py"],
    )

    try:
        provider_server.main()
    except ValueError as err:
        assert str(err) == "bad provider config"
    else:
        raise AssertionError("expected ValueError for config load failure")

    assert "failed loading provider config file path=" in caplog.text
