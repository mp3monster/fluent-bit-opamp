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

"""OpAMP WebSocket transport helpers (header + protobuf payload)."""

from __future__ import annotations


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint cannot be negative")
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            break
    return bytes(out)


def decode_varint(data: bytes) -> tuple[int, int]:
    result = 0
    shift = 0
    for idx, byte in enumerate(data):
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, idx + 1
        shift += 7
        if shift >= 64:
            raise ValueError("varint too long")
    raise ValueError("incomplete varint")


def encode_message(payload: bytes, header: int = 0) -> bytes:
    return encode_varint(header) + payload


def decode_message(message: bytes) -> tuple[int, bytes]:
    header, offset = decode_varint(message)
    return header, message[offset:]
