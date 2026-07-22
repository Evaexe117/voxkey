"""Small runtime files shared between the daemon, the clients and the tray.

The tray polls these files while the daemon writes them, so every write goes
through a temporary file and a rename. A reader then sees either the old
content or the new one, never a truncated line.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from voxkey import paths
from voxkey.config import Config

STATE_OFF = "off"
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_DONE = "done"
STATE_ERROR = "error"

_SOUND_OFF = "off"
_SOUND_ON = "on"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text()
    except OSError:
        return default


def get_language(config: Config) -> str:
    stored = read_text(paths.language_file()).strip()
    return stored or config.language


def set_language(code: str) -> None:
    write_atomic(paths.language_file(), code)


def next_language(current: str, languages: Sequence[str]) -> str:
    """The language after ``current``, wrapping around.

    Unknown codes restart the cycle.
    """
    if not languages:
        return current
    try:
        index = list(languages).index(current)
    except ValueError:
        return languages[0]
    return languages[(index + 1) % len(languages)]


def get_state() -> str:
    return read_text(paths.state_file(), default=STATE_IDLE).strip() or STATE_IDLE


def set_state(value: str) -> None:
    write_atomic(paths.state_file(), value)


def sound_enabled() -> bool:
    return read_text(paths.sound_file(), default=_SOUND_ON).strip() != _SOUND_OFF


def set_sound_enabled(enabled: bool) -> None:
    write_atomic(paths.sound_file(), _SOUND_ON if enabled else _SOUND_OFF)
