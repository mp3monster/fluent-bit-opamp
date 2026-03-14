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

from opamp_provider import config as provider_config
from opamp_provider.config import DEFAULT_DELAYED_COMMS_SECONDS, DEFAULT_SIGNIFICANT_COMMS_SECONDS


def test_load_config_with_overrides(tmp_path: Path) -> None:
    data = {
        "provider": {
            "server_capabilities": ["AcceptsStatus"],
            "delayed_comms_seconds": 10,
            "significant_comms_seconds": 20,
        }
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")

    config = provider_config.load_config_with_overrides(
        config_path=config_path,
        server_capabilities=["AcceptsStatus"],
    )

    assert config.delayed_comms_seconds == 10
    assert config.significant_comms_seconds == 20
    assert config.server_capabilities != 0


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    data = {"provider": {"server_capabilities": ["AcceptsStatus"]}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")

    config = provider_config.load_config_with_overrides(
        config_path=config_path,
        server_capabilities=None,
    )

    assert config.delayed_comms_seconds == DEFAULT_DELAYED_COMMS_SECONDS
    assert config.significant_comms_seconds == DEFAULT_SIGNIFICANT_COMMS_SECONDS


def test_update_comms_thresholds() -> None:
    original = provider_config.ProviderConfig(
        server_capabilities=1,
        delayed_comms_seconds=30,
        significant_comms_seconds=120,
        webui_port=8080,
    )
    provider_config.set_config(original)

    updated = provider_config.update_comms_thresholds(delayed=45, significant=300)
    assert updated.delayed_comms_seconds == 45
    assert updated.significant_comms_seconds == 300
