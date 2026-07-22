"""The resident daemon.

It exists so the Whisper model is loaded once rather than per dictation, and so
the push-to-talk client can be restarted freely without paying for a reload.
One request is served at a time: there is one microphone.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from voxkey import state
from voxkey.config import Config
from voxkey.ipc.protocol import (
    STATUS_RECORDING,
    STATUS_TRANSCRIBING,
    ErrorMessage,
    ProtocolError,
    Reply,
    ResultMessage,
    StatusMessage,
    decode_request,
    encode_reply,
)
from voxkey.transcribe.base import Transcriber

logger = logging.getLogger(__name__)

RECEIVE_CHUNK = 4096
ACCEPT_TIMEOUT_SECS = 0.2


class Recorder(Protocol):
    def record(
        self, wait_secs: float, silence_secs: float
    ) -> npt.NDArray[np.float32] | None:
        """Record one utterance, or return None when nothing was said."""


class FakeRecorder:
    """A Recorder for tests. Returns queued clips, or None for silence."""

    def __init__(self, clips: Sequence[npt.NDArray[np.float32] | None]) -> None:
        self._clips = list(clips)
        self._index = 0

    def record(
        self,
        wait_secs: float,  # noqa: ARG002
        silence_secs: float,  # noqa: ARG002
    ) -> npt.NDArray[np.float32] | None:
        clip = self._clips[min(self._index, len(self._clips) - 1)]
        self._index += 1
        return clip


class Daemon:
    def __init__(
        self,
        transcriber: Transcriber,
        recorder: Recorder,
        socket_path: Path,
        config: Config,
    ) -> None:
        self._transcriber = transcriber
        self._recorder = recorder
        self._socket_path = socket_path
        self._config = config
        self._stopping = threading.Event()

    def _bind(self) -> socket.socket:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # A crash leaves the socket file behind and bind would fail on it.
        self._socket_path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self._socket_path))
        listener.listen(1)
        listener.settimeout(ACCEPT_TIMEOUT_SECS)
        return listener

    def serve_forever(self) -> None:
        listener = self._bind()
        state.set_state(state.STATE_IDLE)
        try:
            while not self._stopping.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    self.handle(connection)
        finally:
            listener.close()
            self._socket_path.unlink(missing_ok=True)
            state.set_state(state.STATE_OFF)

    def stop(self) -> None:
        self._stopping.set()

    def _send(self, connection: socket.socket, reply: Reply) -> None:
        """Send a reply, tolerating a peer that is already gone.

        A disconnected client must never be able to kill the serve loop: no
        reply send is allowed to raise.
        """
        try:
            connection.sendall(encode_reply(reply))
        except OSError as error:
            logger.debug("client gone, dropping reply: %s", error)

    def handle(self, connection: socket.socket) -> None:
        payload = b""
        while True:
            chunk = connection.recv(RECEIVE_CHUNK)
            if not chunk:
                break
            payload += chunk
        try:
            request = decode_request(payload)
        except ProtocolError as error:
            logger.warning("rejected a request: %s", error)
            self._send(connection, ErrorMessage(str(error)))
            return

        try:
            self._send(connection, StatusMessage(STATUS_RECORDING))
            state.set_state(state.STATE_RECORDING)
            audio = self._recorder.record(
                wait_secs=request.wait_secs or self._config.wait_secs,
                silence_secs=request.silence_secs or self._config.silence_secs,
            )
            if audio is None:
                logger.info("no speech detected")
                state.set_state(state.STATE_IDLE)
                self._send(connection, ResultMessage(""))
                return

            self._send(connection, StatusMessage(STATUS_TRANSCRIBING))
            state.set_state(state.STATE_TRANSCRIBING)
            text = self._transcriber.transcribe(
                audio, request.language, request.initial_prompt
            )
            if self._config.log_transcripts:
                logger.info("transcribed: %s", text)
            else:
                logger.info("transcribed %d characters", len(text))
            state.set_state(state.STATE_DONE)
            self._send(connection, ResultMessage(text))
        except Exception as error:  # noqa: BLE001  # one bad request must not kill the daemon
            logger.exception("dictation failed")
            state.set_state(state.STATE_ERROR)
            self._send(connection, ErrorMessage(str(error)))
