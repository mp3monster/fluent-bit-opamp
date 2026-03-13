"""Generated protobufs for the consumer."""

from __future__ import annotations

import importlib
import pathlib


def _generated_exists() -> bool:
    here = pathlib.Path(__file__).resolve().parent
    return (here / "opamp_pb2.py").exists() and (here / "anyvalue_pb2.py").exists()


def _ensure() -> None:
    if _generated_exists():
        return
    from . import ensure

    ensure.generate()


_ensure()

opamp_pb2 = importlib.import_module("opamp_consumer.proto.opamp_pb2")
anyvalue_pb2 = importlib.import_module("opamp_consumer.proto.anyvalue_pb2")
