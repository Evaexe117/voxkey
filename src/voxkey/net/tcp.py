"""Framing for the remote transcription protocol.

    daemon to server    uint32 big-endian header length, JSON header, raw audio
    server to daemon    one JSON object, newline terminated

Audio is float32, mono, 16 kHz. The format is unchanged from dictate so that a
voxkey daemon and a dictate server interoperate during a staged upgrade.

Encoding and decoding are pure functions over byte streams, so the whole
protocol is tested without opening a socket.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import IO

import numpy as np
import numpy.typing as npt

HEADER_LENGTH_FORMAT = ">I"
HEADER_LENGTH_SIZE = 4

#: The header is a small JSON object; 64 KiB is generous.
MAX_HEADER_BYTES = 64 * 1024
#: ~2 hours of 16 kHz float32 mono audio (~64 KiB/s), enough for any
#: dictation while still bounding a malicious or buggy audio_length.
MAX_AUDIO_BYTES = 512 * 1024 * 1024


class RemoteError(RuntimeError):
    """The peer reported a failure, or the frame was unusable."""


@dataclass(frozen=True)
class RemoteRequest:
    language: str
    initial_prompt: str
    audio: npt.NDArray[np.float32]


def encode_request(request: RemoteRequest) -> bytes:
    audio = np.asarray(request.audio, dtype=np.float32)
    payload = audio.tobytes()
    header = json.dumps(
        {
            "language": request.language,
            "initial_prompt": request.initial_prompt,
            "audio_length": len(payload),
        }
    ).encode()
    return struct.pack(HEADER_LENGTH_FORMAT, len(header)) + header + payload


def _read_exactly(stream: IO[bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            got = size - remaining
            raise RemoteError(f"truncated frame: wanted {size} bytes, got {got}")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def decode_request(stream: IO[bytes]) -> RemoteRequest:
    raw_length = _read_exactly(stream, HEADER_LENGTH_SIZE)
    (header_length,) = struct.unpack(HEADER_LENGTH_FORMAT, raw_length)
    if header_length > MAX_HEADER_BYTES:
        raise RemoteError(
            f"header too large: {header_length} bytes exceeds the "
            f"{MAX_HEADER_BYTES} byte limit"
        )
    raw_header_bytes = _read_exactly(stream, header_length)
    try:
        raw_header = raw_header_bytes.decode()
    except UnicodeDecodeError as error:
        raise RemoteError("invalid header: not valid UTF-8") from error
    try:
        header = json.loads(raw_header)
    except (json.JSONDecodeError, RecursionError) as error:
        raise RemoteError(f"invalid header: not valid JSON: {error}") from error
    if not isinstance(header, dict):
        raise RemoteError(
            "invalid header: expected a JSON object, "
            f"got {type(header).__name__}"
        )
    try:
        audio_length = int(header["audio_length"])
    except KeyError as error:
        raise RemoteError("invalid header: missing audio_length") from error
    except (ValueError, TypeError) as error:
        value = header["audio_length"]
        raise RemoteError(
            f"invalid header: audio_length must be a number, "
            f"got {type(value).__name__}"
        ) from error
    if audio_length < 0:
        raise RemoteError(
            f"invalid header: audio_length must not be negative, got {audio_length}"
        )
    if audio_length > MAX_AUDIO_BYTES:
        raise RemoteError(
            f"audio too large: {audio_length} bytes exceeds the "
            f"{MAX_AUDIO_BYTES} byte limit"
        )
    payload = _read_exactly(stream, audio_length)
    audio: npt.NDArray[np.float32] = np.frombuffer(payload, dtype=np.float32)
    return RemoteRequest(
        language=str(header.get("language", "en")),
        initial_prompt=str(header.get("initial_prompt", "")),
        audio=audio,
    )


def encode_response(text: str) -> bytes:
    return json.dumps({"text": text}).encode() + b"\n"


def encode_error(message: str) -> bytes:
    return json.dumps({"error": message}).encode() + b"\n"


def decode_response(payload: bytes) -> str:
    text = payload.decode().strip()
    if not text:
        raise RemoteError("empty response from the transcription server")
    try:
        message = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        raise RemoteError(f"invalid response: not valid JSON: {error}") from error
    if not isinstance(message, dict):
        raise RemoteError(
            "invalid response: expected a JSON object, "
            f"got {type(message).__name__}"
        )
    if "error" in message:
        raise RemoteError(str(message["error"]))
    return str(message.get("text", ""))
