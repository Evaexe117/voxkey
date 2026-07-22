from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from voxkey.config import Config
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
