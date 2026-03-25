"""Ensure protobuf Python files are generated for the consumer."""

from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    """Return the repository root directory resolved from this module location."""
    return pathlib.Path(__file__).resolve().parents[4]


def _proto_dir() -> pathlib.Path:
    """Return the shared proto source directory used for code generation."""
    return _repo_root() / "proto"


def _out_dir() -> pathlib.Path:
    """Return the consumer protobuf output directory."""
    return pathlib.Path(__file__).resolve().parent


def generate() -> None:
    """Run protoc to generate consumer Python modules from repository proto files."""
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
