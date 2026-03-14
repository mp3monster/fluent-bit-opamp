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

from pathlib import Path

from opamp_provider.proto import ensure as proto_ensure


def test_generate_invokes_protoc(tmp_path, monkeypatch) -> None:
    out_dir = tmp_path / "out"
    proto_dir = tmp_path / "proto"
    proto_dir.mkdir()
    (proto_dir / "anyvalue.proto").write_text("syntax = \"proto3\";", encoding="utf-8")
    (proto_dir / "opamp.proto").write_text("syntax = \"proto3\";", encoding="utf-8")

    called = {}

    def fake_check_call(cmd):
        called["cmd"] = cmd

    monkeypatch.setattr(proto_ensure, "_out_dir", lambda: out_dir)
    monkeypatch.setattr(proto_ensure, "_proto_dir", lambda: proto_dir)
    monkeypatch.setattr(proto_ensure.subprocess, "check_call", fake_check_call)

    proto_ensure.generate()

    assert "grpc_tools.protoc" in " ".join(called["cmd"])
    assert str(proto_dir / "anyvalue.proto") in called["cmd"]
    assert str(proto_dir / "opamp.proto") in called["cmd"]
