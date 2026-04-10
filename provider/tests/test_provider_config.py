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

import os
import pathlib
import json

from opamp_provider import config as provider_config


def test_minutes_keep_disconnected_default() -> None:
    """Verify default disconnect retention by loading config from test JSON and comparing to provider default constant."""
    root = pathlib.Path(__file__).resolve().parents[2]
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(root / "tests" / "opamp.json")
    config = provider_config.load_config()
    assert config.minutes_keep_disconnected == provider_config.DEFAULT_MINUTES_KEEP_DISCONNECTED


def test_human_in_loop_and_authorization_defaults_are_disabled() -> None:
    """Verify approval/auth settings default to disabled/none when omitted."""
    root = pathlib.Path(__file__).resolve().parents[2]
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(root / "tests" / "opamp.json")
    config = provider_config.load_config()
    assert config.human_in_loop_approval is False
    assert config.opamp_use_authorization == provider_config.OPAMP_USE_AUTHORIZATION_NONE
    assert config.ui_use_authorization == provider_config.DEFAULT_UI_USE_AUTHORIZATION


def test_latest_docs_url_defaults_when_missing() -> None:
    """Verify latest docs redirect URL falls back to the default when omitted."""
    root = pathlib.Path(__file__).resolve().parents[2]
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(root / "tests" / "opamp.json")
    config = provider_config.load_config()
    assert config.latest_docs_url == provider_config.DEFAULT_LATEST_DOCS_URL


def test_latest_docs_url_loads_from_config(tmp_path) -> None:
    """Verify provider.latest_docs_url is parsed from config."""
    docs_url = "https://example.org/custom-docs"
    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "latest_docs_url": docs_url,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(config_path)

    config = provider_config.load_config()
    assert config.latest_docs_url == docs_url


def test_provider_tls_defaults_to_none_when_missing() -> None:
    """Verify provider TLS remains disabled when provider.tls is absent."""
    root = pathlib.Path(__file__).resolve().parents[2]
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(root / "tests" / "opamp.json")
    config = provider_config.load_config()
    assert config.tls is None


def test_provider_tls_enabled_defaults_true_when_section_present(tmp_path) -> None:
    """Verify provider.tls defaults to enabled when section exists and `enabled` is omitted."""
    cert_file = tmp_path / "provider-server.pem"
    key_file = tmp_path / "provider-server-key.pem"
    cert_file.write_text("dummy cert", encoding="utf-8")
    key_file.write_text("dummy key", encoding="utf-8")

    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "tls": {
                        "cert_file": str(cert_file),
                        "key_file": str(key_file),
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(config_path)

    config = provider_config.load_config()
    assert config.tls is not None
    assert config.tls.cert_file == str(cert_file)
    assert config.tls.key_file == str(key_file)


def test_provider_tls_disabled_when_enabled_flag_false(tmp_path) -> None:
    """Verify provider.tls.enabled=false disables TLS even when TLS section exists."""
    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "tls": {
                        "enabled": False,
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(config_path)

    config = provider_config.load_config()
    assert config.tls is None


def test_state_persistence_defaults_when_missing() -> None:
    """Verify state persistence settings fall back to documented defaults when omitted."""
    root = pathlib.Path(__file__).resolve().parents[2]
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(root / "tests" / "opamp.json")
    config = provider_config.load_config()

    assert config.state_persistence.enabled is False
    assert config.state_persistence.state_file_prefix == "runtime/opamp_server_state"
    assert config.state_persistence.retention_count == 5
    assert config.state_persistence.autosave_interval_seconds_since_change == 600


def test_provider_tls_loads_from_config(tmp_path) -> None:
    """Verify provider.tls cert/key/trust mode are parsed from config."""
    cert_file = tmp_path / "provider-server.pem"
    key_file = tmp_path / "provider-server-key.pem"
    cert_file.write_text("dummy cert", encoding="utf-8")
    key_file.write_text("dummy key", encoding="utf-8")

    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "webui_port": 8080,
                    "tls": {
                        "cert_file": str(cert_file),
                        "key_file": str(key_file),
                        "trust_anchor_mode": provider_config.TLS_TRUST_ANCHOR_PARTIAL_CHAIN,
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(config_path)

    config = provider_config.load_config()

    assert config.tls is not None
    assert config.tls.cert_file == str(cert_file)
    assert config.tls.key_file == str(key_file)
    assert (
        config.tls.trust_anchor_mode
        == provider_config.TLS_TRUST_ANCHOR_PARTIAL_CHAIN
    )


def test_provider_tls_rejects_unsupported_trust_anchor_mode(tmp_path) -> None:
    """Verify invalid provider.tls.trust_anchor_mode raises during startup config load."""
    cert_file = tmp_path / "provider-server.pem"
    key_file = tmp_path / "provider-server-key.pem"
    cert_file.write_text("dummy cert", encoding="utf-8")
    key_file.write_text("dummy key", encoding="utf-8")

    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "tls": {
                        "cert_file": str(cert_file),
                        "key_file": str(key_file),
                        "trust_anchor_mode": "invalid-mode",
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(config_path)

    try:
        provider_config.load_config()
    except ValueError as err:
        assert "provider.tls.trust_anchor_mode" in str(err)
    else:
        raise AssertionError("expected ValueError for unsupported trust anchor mode")


def test_provider_tls_accepts_none_trust_anchor_mode(tmp_path) -> None:
    """Verify provider.tls.trust_anchor_mode accepts `none` for local self-signed mode."""
    cert_file = tmp_path / "provider-server.pem"
    key_file = tmp_path / "provider-server-key.pem"
    cert_file.write_text("dummy cert", encoding="utf-8")
    key_file.write_text("dummy key", encoding="utf-8")

    config_path = tmp_path / "opamp.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "tls": {
                        "cert_file": str(cert_file),
                        "key_file": str(key_file),
                        "trust_anchor_mode": provider_config.TLS_TRUST_ANCHOR_NONE,
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(config_path)

    config = provider_config.load_config()
    assert config.tls is not None
    assert config.tls.trust_anchor_mode == provider_config.TLS_TRUST_ANCHOR_NONE


def test_update_comms_thresholds_updates_retention_count() -> None:
    """Verify update_comms_thresholds applies new state snapshot retention count."""
    provider_config.set_config(
        provider_config.ProviderConfig(
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
                retention_count=5,
            ),
        )
    )

    updated = provider_config.update_comms_thresholds(
        delayed=60,
        significant=300,
        retention_count=9,
    )

    assert updated.state_persistence.retention_count == 9
