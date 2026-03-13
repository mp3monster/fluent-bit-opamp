"""Ensure protobuf Python files are generated for the provider."""

from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[4]


def _proto_dir() -> pathlib.Path:
    return _repo_root() / "proto"


def _out_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def generate() -> None:
    out_dir = _out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    proto_dir = _proto_dir()

    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={out_dir}",
        str(proto_dir / "anyvalue.proto"),
        str(proto_dir / "opamp.proto"),
    ]
    subprocess.check_call(cmd)


if __name__ == "__main__":
    generate()
