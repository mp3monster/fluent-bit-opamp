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
import sys


def pytest_configure() -> None:
    root = pathlib.Path(__file__).resolve().parents[2]
    src = root / "provider" / "src"
    for path in (root, src):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.environ.setdefault("OPAMP_CONFIG_PATH", str(root / "tests" / "opamp.json"))
