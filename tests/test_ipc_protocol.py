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


def test_status_wire_shape_matches_dictate() -> None:
    assert encode_reply(StatusMessage("recording")) == b'{"status": "recording"}\n'
    assert encode_reply(ResultMessage("hi")) == b'{"text": "hi"}\n'
