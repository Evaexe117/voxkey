"""Messages exchanged over the Unix socket.

    client to daemon    one JSON object, then shutdown(SHUT_WR)
    daemon to client    newline delimited JSON objects

The wire shapes are unchanged from dictate, so an old client and a new daemon
still understand each other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import assert_never

STATUS_RECORDING = "recording"
STATUS_TRANSCRIBING = "transcribing"


class ProtocolError(ValueError):
    """A message could not be understood."""


@dataclass(frozen=True)
class DictationRequest:
    language: str = "en"
    initial_prompt: str | None = None
    wait_secs: float | None = None
    silence_secs: float | None = None


@dataclass(frozen=True)
class StatusMessage:
    status: str


@dataclass(frozen=True)
class ResultMessage:
    text: str


@dataclass(frozen=True)
class ErrorMessage:
    message: str


Reply = StatusMessage | ResultMessage | ErrorMessage


def encode_request(request: DictationRequest) -> bytes:
    body: dict[str, object] = {"language": request.language}
    if request.initial_prompt is not None:
        body["initial_prompt"] = request.initial_prompt
    if request.wait_secs is not None:
        body["wait_secs"] = request.wait_secs
    if request.silence_secs is not None:
        body["silence_secs"] = request.silence_secs
    return json.dumps(body).encode()


def _as_optional_str(key: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolError(
            f"{key}: expected a string, found {type(value).__name__}"
        )
    return value


def _as_optional_positive_number(key: str, value: object) -> float | None:
    if value is None:
        return None
    # bool is a subclass of int, and "wait_secs = true" is always a mistake.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(
            f"{key}: expected a number, found {type(value).__name__}"
        )
    number = float(value)
    if number <= 0:
        raise ProtocolError(f"{key}: expected a positive number, found {number}")
    return number


def decode_request(payload: bytes) -> DictationRequest:
    try:
        body = json.loads(payload.decode() or "{}")
    except (ValueError, UnicodeDecodeError) as error:
        raise ProtocolError(f"unreadable request: {error}") from error
    if not isinstance(body, dict):
        raise ProtocolError("request must be a JSON object")
    return DictationRequest(
        language=str(body.get("language", "en")),
        initial_prompt=_as_optional_str("initial_prompt", body.get("initial_prompt")),
        wait_secs=_as_optional_positive_number("wait_secs", body.get("wait_secs")),
        silence_secs=_as_optional_positive_number(
            "silence_secs", body.get("silence_secs")
        ),
    )


def encode_reply(reply: Reply) -> bytes:
    match reply:
        case StatusMessage(status):
            body: dict[str, str] = {"status": status}
        case ResultMessage(text):
            body = {"text": text}
        case ErrorMessage(message):
            body = {"error": message}
        case _:
            assert_never(reply)
    return json.dumps(body).encode() + b"\n"


def decode_reply(payload: bytes) -> Reply:
    """Decode one newline delimited JSON reply.

    A reply is classified by which known key it carries. If more than one is
    present, "status" wins over "text", which wins over "error"; only the
    first match is used and the rest are ignored.
    """
    try:
        body = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError) as error:
        raise ProtocolError(f"unreadable reply: {error}") from error
    if not isinstance(body, dict):
        raise ProtocolError("reply must be a JSON object")
    if "status" in body:
        return StatusMessage(str(body["status"]))
    if "text" in body:
        return ResultMessage(str(body["text"]))
    if "error" in body:
        return ErrorMessage(str(body["error"]))
    raise ProtocolError(f"reply carries no known field: {sorted(body)}")
