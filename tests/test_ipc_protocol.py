from __future__ import annotations

import pytest

from voxkey.ipc.protocol import (
    STATUS_RECORDING,
    DictationRequest,
    ErrorMessage,
    ProtocolError,
    ResultMessage,
    StatusMessage,
    decode_reply,
    decode_request,
    encode_reply,
    encode_request,
)


def test_request_round_trips() -> None:
    original = DictationRequest(
        language="fr", initial_prompt="Terms: a.", wait_secs=5.0, silence_secs=2.0
    )
    assert decode_request(encode_request(original)) == original


def test_request_defaults_are_filled_in() -> None:
    decoded = decode_request(b'{"language": "en"}')
    assert decoded.language == "en"
    assert decoded.initial_prompt is None
    assert decoded.wait_secs is None
    assert decoded.silence_secs is None


def test_malformed_request_is_reported() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b"not json")


def test_request_rejects_non_string_initial_prompt() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b'{"language":"en","initial_prompt":42}')


def test_request_rejects_non_numeric_wait_secs() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b'{"language":"en","wait_secs":"five"}')


def test_request_rejects_non_numeric_silence_secs() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b'{"language":"en","silence_secs":"five"}')


def test_request_rejects_bool_wait_secs() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b'{"language":"en","wait_secs":true}')


def test_request_rejects_zero_or_negative_wait_secs() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b'{"language":"en","wait_secs":0}')
    with pytest.raises(ProtocolError):
        decode_request(b'{"language":"en","wait_secs":-1.0}')


def test_request_accepts_null_optional_fields() -> None:
    decoded = decode_request(
        b'{"language":"en","initial_prompt":null,'
        b'"wait_secs":null,"silence_secs":null}'
    )
    assert decoded.initial_prompt is None
    assert decoded.wait_secs is None
    assert decoded.silence_secs is None


def test_status_reply_round_trips() -> None:
    assert decode_reply(encode_reply(StatusMessage(STATUS_RECORDING))) == StatusMessage(
        STATUS_RECORDING
    )


def test_result_reply_round_trips() -> None:
    assert decode_reply(encode_reply(ResultMessage("hello"))) == ResultMessage("hello")


def test_error_reply_round_trips() -> None:
    assert decode_reply(encode_reply(ErrorMessage("boom"))) == ErrorMessage("boom")


def test_every_reply_is_newline_terminated() -> None:
    for reply in (StatusMessage("recording"), ResultMessage("x"), ErrorMessage("y")):
        assert encode_reply(reply).endswith(b"\n")


def test_reply_without_a_known_field_is_reported() -> None:
    with pytest.raises(ProtocolError):
        decode_reply(b'{"unexpected": 1}')


def test_reply_precedence_is_status_then_text_then_error() -> None:
    assert decode_reply(b'{"status": "recording", "text": "x", "error": "y"}') == (
        StatusMessage("recording")
    )
    assert decode_reply(b'{"text": "x", "error": "y"}') == ResultMessage("x")


def test_status_wire_shape_matches_dictate() -> None:
    assert encode_reply(StatusMessage("recording")) == b'{"status": "recording"}\n'
    assert encode_reply(ResultMessage("hi")) == b'{"text": "hi"}\n'


def test_non_finite_duration_is_rejected() -> None:
    for payload in (b'{"language":"en","wait_secs":NaN}',
                    b'{"language":"en","silence_secs":Infinity}'):
        with pytest.raises(ProtocolError, match="finite"):
            decode_request(payload)
