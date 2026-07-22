"""Talking to the daemon."""

from __future__ import annotations

import socket
from collections.abc import Callable
from pathlib import Path

from voxkey.ipc.protocol import (
    DictationRequest,
    ErrorMessage,
    ResultMessage,
    StatusMessage,
    decode_reply,
    encode_request,
)

RECEIVE_CHUNK = 4096


class DaemonUnavailableError(RuntimeError):
    """The daemon is not listening on the socket."""


def dictate_once(
    socket_path: Path,
    request: DictationRequest,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """Ask the daemon for one dictation and return the text."""
    # The socket is created inside the with-block so it is closed on every exit
    # path, including a connect() that raises something other than the two
    # not-running errors below.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        try:
            connection.connect(str(socket_path))
        except (FileNotFoundError, ConnectionRefusedError) as error:
            raise DaemonUnavailableError(
                f"the voxkey daemon is not running on {socket_path}. Start it with "
                f"'voxkey serve', or 'systemctl --user start voxkey.service'."
            ) from error

        connection.sendall(encode_request(request))
        connection.shutdown(socket.SHUT_WR)
        buffer = b""
        while True:
            chunk = connection.recv(RECEIVE_CHUNK)
            if not chunk:
                break
            buffer += chunk

    text = ""
    for line in buffer.splitlines():
        if not line.strip():
            continue
        reply = decode_reply(line)
        match reply:
            case StatusMessage(status) if on_status is not None:
                on_status(status)
            case ResultMessage(result):
                text = result
            case ErrorMessage(message):
                raise RuntimeError(message)
            case _:
                pass
    return text
