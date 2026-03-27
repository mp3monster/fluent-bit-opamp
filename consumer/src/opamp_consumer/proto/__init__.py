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

"""Generated protobufs for the consumer."""

from __future__ import annotations

import importlib
import pathlib
import sys


def _generated_exists() -> bool:
    """Return True when generated consumer protobuf modules already exist on disk."""
    here = pathlib.Path(__file__).resolve().parent
    return (here / "opamp_pb2.py").exists() and (here / "anyvalue_pb2.py").exists()


def _ensure() -> None:
    """Generate protobuf Python modules on demand when generated files are missing."""
    if _generated_exists():
        return
    from . import ensure

    ensure.generate()


_ensure()

_proto_dir = pathlib.Path(__file__).resolve().parent
if str(_proto_dir) not in sys.path:
    sys.path.insert(0, str(_proto_dir))

opamp_pb2 = importlib.import_module("opamp_consumer.proto.opamp_pb2")
anyvalue_pb2 = importlib.import_module("opamp_consumer.proto.anyvalue_pb2")
