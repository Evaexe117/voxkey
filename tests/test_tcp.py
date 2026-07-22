from __future__ import annotations

import io
import json
import struct

import numpy as np
import pytest

from voxkey.net.tcp import (
    MAX_AUDIO_BYTES,
    MAX_HEADER_BYTES,
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


def _frame_with_header_bytes(header: bytes) -> bytes:
    return struct.pack(">I", len(header)) + header


def test_invalid_json_header_is_reported() -> None:
    frame = _frame_with_header_bytes(b"not json")
    with pytest.raises(RemoteError, match="header"):
        decode_request(io.BytesIO(frame))


def test_header_that_is_a_json_array_is_reported() -> None:
    frame = _frame_with_header_bytes(b"[1, 2, 3]")
    with pytest.raises(RemoteError, match="header"):
        decode_request(io.BytesIO(frame))


def test_header_missing_audio_length_is_reported() -> None:
    header = json.dumps({"language": "en", "initial_prompt": ""}).encode()
    frame = _frame_with_header_bytes(header)
    with pytest.raises(RemoteError, match="audio_length"):
        decode_request(io.BytesIO(frame))


def test_negative_audio_length_is_reported() -> None:
    header = json.dumps(
        {"language": "en", "initial_prompt": "", "audio_length": -4}
    ).encode()
    frame = _frame_with_header_bytes(header)
    with pytest.raises(RemoteError, match="audio_length"):
        decode_request(io.BytesIO(frame))


def test_non_json_response_is_reported() -> None:
    with pytest.raises(RemoteError, match="response"):
        decode_response(b"not json\n")


def test_response_that_is_a_json_array_is_reported() -> None:
    with pytest.raises(RemoteError, match="response"):
        decode_response(b"[1, 2, 3]\n")


def test_response_that_is_a_bare_number_is_reported() -> None:
    with pytest.raises(RemoteError, match="response"):
        decode_response(b"42\n")


def test_audio_length_string_is_reported() -> None:
    header = json.dumps(
        {"language": "en", "initial_prompt": "", "audio_length": "abc"}
    ).encode()
    frame = _frame_with_header_bytes(header)
    with pytest.raises(RemoteError, match="audio_length"):
        decode_request(io.BytesIO(frame))


def test_audio_length_list_is_reported() -> None:
    header = json.dumps(
        {"language": "en", "initial_prompt": "", "audio_length": [1]}
    ).encode()
    frame = _frame_with_header_bytes(header)
    with pytest.raises(RemoteError, match="audio_length"):
        decode_request(io.BytesIO(frame))


def test_audio_length_null_is_reported() -> None:
    header = json.dumps(
        {"language": "en", "initial_prompt": "", "audio_length": None}
    ).encode()
    frame = _frame_with_header_bytes(header)
    with pytest.raises(RemoteError, match="audio_length"):
        decode_request(io.BytesIO(frame))


def test_non_utf8_header_is_reported() -> None:
    frame = _frame_with_header_bytes(b"\xff\xfe invalid utf8")
    with pytest.raises(RemoteError, match="UTF-8"):
        decode_request(io.BytesIO(frame))


def test_header_length_over_the_limit_is_rejected_without_reading_it() -> None:
    # The stream carries no bytes past the declared (oversized) header
    # length. If the code tried to read that many bytes anyway it would
    # raise "truncated frame" instead, so this also proves the limit check
    # runs before any attempt to read the declared amount.
    frame = struct.pack(">I", MAX_HEADER_BYTES + 1)
    with pytest.raises(RemoteError, match="header too large"):
        decode_request(io.BytesIO(frame))


def test_audio_length_over_the_limit_is_rejected_without_reading_it() -> None:
    header = json.dumps(
        {"language": "en", "initial_prompt": "", "audio_length": MAX_AUDIO_BYTES + 1}
    ).encode()
    frame = _frame_with_header_bytes(header)
    with pytest.raises(RemoteError, match="audio too large"):
        decode_request(io.BytesIO(frame))
