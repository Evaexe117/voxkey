from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import numpy as np
import pytest

from voxkey.net.tcp import RemoteError, decode_request, encode_error, encode_response
from voxkey.transcribe.remote import RemoteTranscriber, parse_address

TEST_CONNECT_TIMEOUT_SECS = 0.5
SLOW_SERVER_DELAY_SECS = 1.0


@pytest.fixture
def echo_server() -> Iterator[tuple[tuple[str, int], list[str]]]:
    """A one-shot server that decodes the request and answers its language."""
    received: list[str] = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection, connection.makefile("rb") as stream:
            request = decode_request(stream)
            received.append(request.language)
            connection.sendall(encode_response(f"heard {len(request.audio)} samples"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    host, port = listener.getsockname()
    yield (host, port), received
    thread.join(timeout=5)
    listener.close()


def test_parse_address_splits_host_and_port() -> None:
    assert parse_address("192.168.1.10:5555") == ("192.168.1.10", 5555)


def test_parse_address_handles_ipv6_style_hosts() -> None:
    assert parse_address("::1:5555") == ("::1", 5555)


def test_parse_address_rejects_a_missing_port() -> None:
    with pytest.raises(ValueError, match="HOST:PORT"):
        parse_address("192.168.1.10")


def test_round_trip_against_a_real_socket(
    echo_server: tuple[tuple[str, int], list[str]],
) -> None:
    address, received = echo_server
    transcriber = RemoteTranscriber(address)
    text = transcriber.transcribe(np.zeros(3, dtype=np.float32), "fr", None)
    assert text == "heard 3 samples"
    assert received == ["fr"]


@pytest.fixture
def slow_echo_server() -> Iterator[tuple[tuple[str, int], list[str]]]:
    """A server that replies well after the connect timeout has elapsed."""
    received: list[str] = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection, connection.makefile("rb") as stream:
            request = decode_request(stream)
            received.append(request.language)
            threading.Event().wait(SLOW_SERVER_DELAY_SECS)
            connection.sendall(encode_response(f"heard {len(request.audio)} samples"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    host, port = listener.getsockname()
    yield (host, port), received
    thread.join(timeout=5)
    listener.close()


def test_a_reply_slower_than_the_connect_timeout_still_arrives(
    slow_echo_server: tuple[tuple[str, int], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The connect timeout must not double as a bound on how long the server
    # is allowed to take to answer.
    monkeypatch.setattr(
        "voxkey.transcribe.remote.CONNECT_TIMEOUT_SECS", TEST_CONNECT_TIMEOUT_SECS
    )
    address, received = slow_echo_server
    transcriber = RemoteTranscriber(address)
    text = transcriber.transcribe(np.zeros(3, dtype=np.float32), "fr", None)
    assert text == "heard 3 samples"
    assert received == ["fr"]


def test_server_error_surfaces_as_remote_error() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection, connection.makefile("rb") as stream:
            decode_request(stream)
            connection.sendall(encode_error("model exploded"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        transcriber = RemoteTranscriber(listener.getsockname())
        with pytest.raises(RemoteError, match="model exploded"):
            transcriber.transcribe(np.zeros(1, dtype=np.float32), "en", None)
    finally:
        thread.join(timeout=5)
        listener.close()


def test_parse_address_rejects_an_out_of_range_port() -> None:
    with pytest.raises(ValueError, match="out of range"):
        parse_address("host:99999999999")
    with pytest.raises(ValueError, match="out of range"):
        parse_address("host:0")
