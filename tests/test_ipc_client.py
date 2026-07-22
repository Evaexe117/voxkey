from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest

from voxkey.config import Config
from voxkey.ipc.client import DaemonUnavailableError, dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.ipc.server import Daemon, FakeRecorder
from voxkey.transcribe.base import FakeTranscriber


def test_client_and_daemon_agree(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    socket_path = tmp_path / "voxkey.sock"
    daemon = Daemon(
        transcriber=FakeTranscriber(["round trip"]),
        recorder=FakeRecorder([np.ones(160, dtype=np.float32)]),
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if socket_path.exists():
                break
            threading.Event().wait(0.01)
        seen: list[str] = []
        text = dictate_once(
            socket_path, DictationRequest(language="en"), on_status=seen.append
        )
        assert text == "round trip"
        assert seen == ["recording", "transcribing"]
    finally:
        daemon.stop()
        thread.join(timeout=5)


def test_absent_daemon_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(DaemonUnavailableError, match="not running"):
        dictate_once(tmp_path / "absent.sock", DictationRequest())
