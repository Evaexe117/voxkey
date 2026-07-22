from __future__ import annotations

import io
import struct

import numpy as np
import pytest

from voxkey.net.tcp import (
    RemoteError,
    RemoteRequest,
    decode_request,
    decode_response,
    encode_error,
    encode_request,
    encode_response,
)


def test_request_round_trips() -> None:
    audio = np.array([0.0, 0.5, -0.5], dtype=np.float32)
    original = RemoteRequest(language="fr", initial_prompt="Terms: a.", audio=audio)
    decoded = decode_request(io.BytesIO(encode_request(original)))
    assert decoded.language == "fr"
    assert decoded.initial_prompt == "Terms: a."
    np.testing.assert_array_equal(decoded.audio, audio)


def test_frame_starts_with_a_big_endian_header_length() -> None:
    request = RemoteRequest("en", "", np.zeros(1, dtype=np.float32))
    frame = encode_request(request)
    (header_length,) = struct.unpack(">I", frame[:4])
    assert header_length == len(frame) - 4 - 4  # one float32 of audio


def test_audio_is_coerced_to_float32() -> None:
    request = RemoteRequest("en", "", np.array([1.0, 2.0], dtype=np.float64))
    decoded = decode_request(io.BytesIO(encode_request(request)))
    assert decoded.audio.dtype == np.float32


def test_truncated_audio_is_reported() -> None:
    frame = encode_request(RemoteRequest("en", "", np.zeros(4, dtype=np.float32)))
    with pytest.raises(RemoteError, match="truncated"):
        decode_request(io.BytesIO(frame[:-4]))


def test_truncated_header_is_reported() -> None:
    with pytest.raises(RemoteError, match="truncated"):
        decode_request(io.BytesIO(b"\x00\x00"))


def test_response_round_trips() -> None:
    assert decode_response(encode_response("hello")) == "hello"


def test_response_is_newline_terminated() -> None:
    assert encode_response("hello").endswith(b"\n")


def test_error_response_raises() -> None:
    with pytest.raises(RemoteError, match="model exploded"):
        decode_response(encode_error("model exploded"))


def test_empty_response_is_reported() -> None:
    with pytest.raises(RemoteError, match="empty"):
        decode_response(b"")
