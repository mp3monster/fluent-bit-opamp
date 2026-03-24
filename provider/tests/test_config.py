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

from opamp_provider import config as provider_config


def test_minutes_keep_disconnected_default() -> None:
    """Verify default disconnect retention by loading config from test JSON and comparing to provider default constant."""
    root = pathlib.Path(__file__).resolve().parents[2]
    os.environ[provider_config.ENV_OPAMP_CONFIG_PATH] = str(root / "tests" / "opamp.json")
    config = provider_config.load_config()
    assert config.minutes_keep_disconnected == provider_config.DEFAULT_MINUTES_KEEP_DISCONNECTED
