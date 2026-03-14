"""Generated protobufs for the consumer."""

from __future__ import annotations

import importlib
import pathlib
import sys


def _generated_exists() -> bool:
    here = pathlib.Path(__file__).resolve().parent
    return (here / "opamp_pb2.py").exists() and (here / "anyvalue_pb2.py").exists()


def _ensure() -> None:
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
