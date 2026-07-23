"""Transcription delegated to another machine on the local network."""

from __future__ import annotations

import socket
import time

import numpy as np
import numpy.typing as npt

from voxkey.net.tcp import RemoteError, RemoteRequest, decode_response, encode_request

RECEIVE_CHUNK = 4096
CONNECT_TIMEOUT_SECS = 10.0
# Generous upper bound on the whole read, so a genuinely dead or half-open
# server is eventually given up on rather than hanging the client forever,
# while still leaving room for a long transcription on a slow remote.
READ_TIMEOUT_SECS = 300.0
#: The response is a small JSON object carrying the transcribed text; 16 MiB
#: is far beyond any real transcription and bounds a hostile or buggy server
#: that streams data forever.
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def parse_address(text: str) -> tuple[str, int]:
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ValueError(f"expected HOST:PORT, found {text!r}")
    number = int(port)
    # isdigit() accepts arbitrarily large values; reject an out-of-range port
    # here with a clear message rather than letting bind() raise OverflowError.
    if not 1 <= number <= 65535:
        raise ValueError(f"port out of range (1-65535): {number}")
    return host, number


class RemoteTranscriber:
    """Transcriber that ships the audio to a voxkey server and reads the text back."""

    def __init__(self, address: tuple[str, int]) -> None:
        self._address = address

    def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        language: str,
        initial_prompt: str | None,
    ) -> str:
        frame = encode_request(
            RemoteRequest(
                language=language,
                initial_prompt=initial_prompt or "",
                audio=np.asarray(audio, dtype=np.float32),
            )
        )
        with socket.create_connection(
            self._address, CONNECT_TIMEOUT_SECS
        ) as connection:
            # create_connection leaves its connect timeout on the socket,
            # which would otherwise also cap the read below and cut off a
            # transcription that legitimately takes longer than that to
            # produce. The read deadline is absolute (monotonic clock), not
            # per-recv: a peer trickling one byte per timeout window would
            # otherwise keep the daemon blocked indefinitely.
            connection.settimeout(READ_TIMEOUT_SECS)
            connection.sendall(frame)
            connection.shutdown(socket.SHUT_WR)
            deadline = time.monotonic() + READ_TIMEOUT_SECS
            total = 0
            chunks: list[bytes] = []
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "timed out reading the transcription response "
                        f"({READ_TIMEOUT_SECS:.0f}s deadline)"
                    )
                connection.settimeout(remaining)
                chunk = connection.recv(RECEIVE_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise RemoteError(
                        f"response too large: over {MAX_RESPONSE_BYTES} bytes"
                    )
                chunks.append(chunk)
        return decode_response(b"".join(chunks))
