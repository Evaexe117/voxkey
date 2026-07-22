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
BYTES_PER_SAMPLE = 4


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
    header = json.loads(_read_exactly(stream, header_length).decode())
    payload = _read_exactly(stream, int(header["audio_length"]))
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
    message = json.loads(text)
    if "error" in message:
        raise RemoteError(str(message["error"]))
    return str(message.get("text", ""))
