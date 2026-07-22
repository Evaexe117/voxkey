from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from voxkey import paths, runtime
from voxkey.audio.devices import DeviceInfo
from voxkey.config import Config
from voxkey.net.tcp import RemoteRequest, decode_response, encode_request
from voxkey.transcribe.base import FakeTranscriber
from voxkey.transcribe.remote import RemoteTranscriber


def test_a_configured_remote_selects_the_remote_transcriber() -> None:
    transcriber = runtime.build_transcriber(Config(remote="10.0.0.2:5555"))
    assert isinstance(transcriber, RemoteTranscriber)


def test_no_remote_loads_a_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[str] = []

    def fake_load_model(choice: object) -> object:
        loaded.append(str(choice))
        return object()

    monkeypatch.setattr(runtime, "load_model", fake_load_model)
    monkeypatch.setattr(runtime, "detect_cuda", lambda: False)
    runtime.build_transcriber(Config())
    assert loaded and "small" in loaded[0]


def test_a_configured_model_name_overrides_the_automatic_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(
        runtime, "load_model", lambda choice: loaded.append(choice.name)
    )
    monkeypatch.setattr(runtime, "detect_cuda", lambda: False)
    runtime.build_transcriber(Config(model="large-v3"))
    assert loaded == ["large-v3"]


def test_stop_requested_consumes_the_flag(xdg: Path) -> None:  # noqa: ARG001
    assert runtime.stop_requested() is False
    paths.stop_file().parent.mkdir(parents=True, exist_ok=True)
    paths.stop_file().write_text("stop")
    assert runtime.stop_requested() is True
    assert runtime.stop_requested() is False


def test_device_listing_names_both_kinds() -> None:
    listing = runtime.format_devices(
        [DeviceInfo(index=1, name="pipewire", max_input_channels=2)],
        ["/dev/input/event3"],
    )
    assert "pipewire" in listing
    assert "/dev/input/event3" in listing


@pytest.fixture
def tcp_server() -> Iterator[tuple[tuple[str, int], FakeTranscriber]]:
    transcriber = FakeTranscriber(["server heard you"])
    # Take a free port from the kernel, then release it so run_tcp_server can
    # bind it itself. getsockname must be read before the socket is closed.
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_socket.bind(("127.0.0.1", 0))
    address = probe_socket.getsockname()
    probe_socket.close()
    stop = threading.Event()
    thread = threading.Thread(
        target=runtime.run_tcp_server, args=(transcriber, address, stop), daemon=True
    )
    thread.start()
    for _ in range(200):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.connect(address)
        except OSError:
            probe.close()
            threading.Event().wait(0.01)
            continue
        else:
            probe.close()
            break
    yield address, transcriber
    stop.set()
    thread.join(timeout=5)


def test_the_tcp_server_transcribes_what_it_is_sent(
    tcp_server: tuple[tuple[str, int], FakeTranscriber],
) -> None:
    address, transcriber = tcp_server
    frame = encode_request(
        RemoteRequest("fr", "Terms: a.", np.ones(32, dtype=np.float32))
    )
    with socket.create_connection(address, 5) as connection:
        connection.sendall(frame)
        connection.shutdown(socket.SHUT_WR)
        payload = b""
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            payload += chunk
    assert decode_response(payload) == "server heard you"
    assert transcriber.calls == [("fr", "Terms: a.", 32)]


def test_a_silent_client_does_not_wedge_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A short per-connection timeout keeps the test fast.
    monkeypatch.setattr(runtime, "CONNECTION_TIMEOUT_SECS", 0.3)
    transcriber = FakeTranscriber(["server heard you"])
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_socket.bind(("127.0.0.1", 0))
    address = probe_socket.getsockname()
    probe_socket.close()
    stop = threading.Event()
    thread = threading.Thread(
        target=runtime.run_tcp_server, args=(transcriber, address, stop), daemon=True
    )
    thread.start()
    silent_client: socket.socket | None = None
    try:
        for _ in range(200):
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.connect(address)
            except OSError:
                probe.close()
                threading.Event().wait(0.01)
                continue
            else:
                probe.close()
                break

        silent_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        silent_client.connect(address)
        # Deliberately never send anything and never close: this must not
        # prevent a well-behaved client, connected right after, from being
        # served once the silent connection's read times out.

        frame = encode_request(
            RemoteRequest("fr", "Terms: a.", np.ones(4, dtype=np.float32))
        )
        with socket.create_connection(address, 5) as connection:
            connection.sendall(frame)
            connection.shutdown(socket.SHUT_WR)
            payload = b""
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                payload += chunk
        assert decode_response(payload) == "server heard you"
    finally:
        if silent_client is not None:
            silent_client.close()
        stop.set()
        thread.join(timeout=5)


def test_tcp_server_survives_a_client_that_disconnects_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "CONNECTION_TIMEOUT_SECS", 0.3)
    transcriber = FakeTranscriber(["server heard you"])
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_socket.bind(("127.0.0.1", 0))
    address = probe_socket.getsockname()
    probe_socket.close()
    stop = threading.Event()
    thread = threading.Thread(
        target=runtime.run_tcp_server, args=(transcriber, address, stop), daemon=True
    )
    thread.start()
    try:
        for _ in range(200):
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.connect(address)
            except OSError:
                probe.close()
                threading.Event().wait(0.01)
                continue
            else:
                probe.close()
                break

        # A client that sends a full frame then closes without reading the
        # reply: the server's sendall must not crash the accept loop.
        frame = encode_request(
            RemoteRequest("fr", "Terms: a.", np.ones(4, dtype=np.float32))
        )
        rude = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rude.connect(address)
        rude.sendall(frame)
        rude.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        rude.close()  # RST, so the server's reply send fails
        threading.Event().wait(0.2)

        # A well-behaved client must still be served afterwards.
        with socket.create_connection(address, 5) as connection:
            connection.sendall(frame)
            connection.shutdown(socket.SHUT_WR)
            payload = b""
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                payload += chunk
        assert decode_response(payload) == "server heard you"
        assert thread.is_alive()
    finally:
        stop.set()
        thread.join(timeout=5)
