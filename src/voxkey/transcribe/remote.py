"""Transcription delegated to another machine on the local network."""

from __future__ import annotations

import socket

import numpy as np
import numpy.typing as npt

from voxkey.net.tcp import RemoteRequest, decode_response, encode_request

RECEIVE_CHUNK = 4096
CONNECT_TIMEOUT_SECS = 10.0


def parse_address(text: str) -> tuple[str, int]:
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ValueError(f"expected HOST:PORT, found {text!r}")
    return host, int(port)


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
            connection.sendall(frame)
            connection.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = connection.recv(RECEIVE_CHUNK)
                if not chunk:
                    break
                chunks.append(chunk)
        return decode_response(b"".join(chunks))
