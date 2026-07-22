"""Putting the transcribed text where it can be pasted.

``xsel`` rather than ``wl-copy``: ``wtype`` does not work under GNOME Wayland,
and ``xsel`` is focus independent, which matters because the dictation ends
while the focus is wherever the user left it.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

logger = logging.getLogger(__name__)

CLIPBOARD_COMMAND = ["xsel", "--clipboard", "--input"]

Runner = Callable[[list[str], bytes], int]


def _run(command: list[str], payload: bytes) -> int:
    process = subprocess.run(command, input=payload, check=False)
    return process.returncode


def copy(text: str, runner: Runner | None = None) -> bool:
    """Copy ``text`` to the clipboard. Returns whether it worked."""
    execute = runner if runner is not None else _run
    try:
        code = execute(CLIPBOARD_COMMAND, text.encode())
    except FileNotFoundError:
        logger.error("xsel is not installed, cannot reach the clipboard")
        return False
    if code != 0:
        logger.error("xsel exited with %s", code)
        return False
    return True
