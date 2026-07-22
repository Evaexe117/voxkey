from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from voxkey.config import Config
from voxkey.ipc import server as server_module
from voxkey.ipc.protocol import (
    STATUS_RECORDING,
    STATUS_TRANSCRIBING,
    DictationRequest,
    ErrorMessage,
    ResultMessage,
    StatusMessage,
    decode_reply,
    encode_request,
)
from voxkey.ipc.server import Daemon, FakeRecorder
from voxkey.transcribe.base import FakeTranscriber


@pytest.fixture
def daemon(
    xdg: Path,  # noqa: ARG001
    tmp_path: Path,
) -> Iterator[tuple[Daemon, Path, FakeTranscriber]]:
    socket_path = tmp_path / "voxkey.sock"
    transcriber = FakeTranscriber(["transcribed text"])
    recorder = FakeRecorder([np.ones(160, dtype=np.float32)])
    instance = Daemon(
        transcriber=transcriber,
        recorder=recorder,
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    for _ in range(200):
        if socket_path.exists():
            break
        threading.Event().wait(0.01)
    yield instance, socket_path, transcriber
    instance.stop()
    thread.join(timeout=5)


def _dictate(socket_path: Path, request: DictationRequest) -> list[object]:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))
    with client:
        client.sendall(encode_request(request))
        client.shutdown(socket.SHUT_WR)
        buffer = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            buffer += chunk
    return [decode_reply(line) for line in buffer.splitlines() if line.strip()]


def test_the_socket_is_created(daemon: tuple[Daemon, Path, FakeTranscriber]) -> None:
    _instance, socket_path, _transcriber = daemon
    assert socket_path.exists()


def test_a_dictation_streams_status_then_text(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, _transcriber = daemon
    replies = _dictate(socket_path, DictationRequest(language="en"))
    assert replies == [
        StatusMessage(STATUS_RECORDING),
        StatusMessage(STATUS_TRANSCRIBING),
        ResultMessage("transcribed text"),
    ]


def test_the_request_language_reaches_the_transcriber(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, transcriber = daemon
    _dictate(socket_path, DictationRequest(language="fr", initial_prompt="Terms: a."))
    assert transcriber.calls == [("fr", "Terms: a.", 160)]


def test_silence_is_reported_rather_than_transcribed(
    xdg: Path,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "silent.sock"
    transcriber = FakeTranscriber(["should not be called"])
    instance = Daemon(
        transcriber=transcriber,
        recorder=FakeRecorder([None]),
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    for _ in range(200):
        if socket_path.exists():
            break
        threading.Event().wait(0.01)
    try:
        replies = _dictate(socket_path, DictationRequest())
        assert replies[-1] == ResultMessage("")
        assert transcriber.calls == []
    finally:
        instance.stop()
        thread.join(timeout=5)


def test_a_malformed_request_yields_an_error_reply(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, _transcriber = daemon
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))
    with client:
        client.sendall(b"not json")
        client.shutdown(socket.SHUT_WR)
        buffer = client.recv(4096)
    assert isinstance(decode_reply(buffer.strip()), ErrorMessage)


class _GatedRecorder:
    """Blocks record() until told to proceed, so a test can control timing."""

    def __init__(
        self, ready: threading.Event, clip: npt.NDArray[np.float32]
    ) -> None:
        self._ready = ready
        self._clip = clip

    def record(
        self,
        wait_secs: float,  # noqa: ARG002
        silence_secs: float,  # noqa: ARG002
    ) -> npt.NDArray[np.float32] | None:
        self._ready.wait(timeout=5)
        return self._clip


def test_a_client_that_disconnects_before_reading_does_not_kill_the_daemon(
    xdg: Path,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "disconnect.sock"
    transcriber = FakeTranscriber(["transcribed text"])
    ready = threading.Event()
    recorder = _GatedRecorder(ready, np.ones(160, dtype=np.float32))
    instance = Daemon(
        transcriber=transcriber,
        recorder=recorder,
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if socket_path.exists():
                break
            threading.Event().wait(0.01)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(socket_path))
        client.sendall(encode_request(DictationRequest()))
        client.shutdown(socket.SHUT_WR)
        # Disconnect before the daemon can reply. record() is still blocked
        # on `ready`, so this close is guaranteed to land before any of the
        # daemon's sendall calls.
        client.close()
        threading.Event().wait(0.05)
        ready.set()

        # The daemon must still be alive and able to serve a well-behaved
        # request afterwards.
        replies = _dictate(socket_path, DictationRequest())
        assert replies[-1] == ResultMessage("transcribed text")
    finally:
        ready.set()
        instance.stop()
        thread.join(timeout=5)


def test_an_oversized_request_is_rejected_and_the_daemon_keeps_serving(
    xdg: Path,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A small limit keeps the test fast without weakening the assertion:
    # the daemon must reject anything past its configured cap.
    monkeypatch.setattr(server_module, "MAX_REQUEST_BYTES", 64)
    socket_path = tmp_path / "oversized.sock"
    transcriber = FakeTranscriber(["transcribed text"])
    recorder = FakeRecorder([np.ones(160, dtype=np.float32)])
    instance = Daemon(
        transcriber=transcriber,
        recorder=recorder,
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if socket_path.exists():
                break
            threading.Event().wait(0.01)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(socket_path))
        with client:
            client.sendall(b"x" * 200)
            client.shutdown(socket.SHUT_WR)
            buffer = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                buffer += chunk
        reply = decode_reply(buffer.strip())
        assert isinstance(reply, ErrorMessage)
        assert "too large" in reply.message

        # The daemon must not have been brought down by the rejection.
        replies = _dictate(socket_path, DictationRequest())
        assert replies[-1] == ResultMessage("transcribed text")
    finally:
        instance.stop()
        thread.join(timeout=5)


def test_two_dictations_in_a_row_both_work(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, _transcriber = daemon
    first = _dictate(socket_path, DictationRequest())
    second = _dictate(socket_path, DictationRequest())
    assert first[-1] == ResultMessage("transcribed text")
    assert second[-1] == ResultMessage("transcribed text")


def test_a_stale_socket_file_is_replaced(
    xdg: Path,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "stale.sock"
    socket_path.write_text("not a socket")
    instance = Daemon(
        transcriber=FakeTranscriber(["x"]),
        recorder=FakeRecorder([np.ones(16, dtype=np.float32)]),
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if socket_path.is_socket():
                break
            threading.Event().wait(0.01)
        assert socket_path.is_socket()
    finally:
        instance.stop()
        thread.join(timeout=5)
