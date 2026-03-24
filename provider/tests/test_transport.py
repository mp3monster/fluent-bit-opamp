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

import pytest

from opamp_provider.transport import (
    decode_message,
    decode_varint,
    encode_message,
    encode_varint,
)


def test_encode_decode_varint_round_trip() -> None:
    """Verify varint round-trip correctness by encoding an integer and asserting decoded value and consumed byte count."""
    value = 300
    encoded = encode_varint(value)
    decoded, size = decode_varint(encoded)
    assert decoded == value
    assert size == len(encoded)


def test_encode_varint_rejects_negative() -> None:
    """Verify encoder validation by passing a negative integer and asserting a `ValueError` is raised."""
    with pytest.raises(ValueError, match="varint cannot be negative"):
        encode_varint(-1)


def test_decode_varint_incomplete() -> None:
    """Verify incomplete varint handling by decoding a continuation byte without terminator and asserting `ValueError`."""
    with pytest.raises(ValueError, match="incomplete varint"):
        decode_varint(bytes([0x80]))


def test_decode_varint_too_long() -> None:
    """Verify oversized varint protection by decoding a 10-byte continuation stream and asserting `ValueError`."""
    with pytest.raises(ValueError, match="varint too long"):
        decode_varint(bytes([0x80] * 10))


def test_encode_decode_message() -> None:
    """Verify framed message round-trip by encoding payload/header and asserting decoded header and payload match inputs."""
    payload = b"hello"
    header = 5
    message = encode_message(payload, header=header)
    decoded_header, decoded_payload = decode_message(message)
    assert decoded_header == header
    assert decoded_payload == payload
