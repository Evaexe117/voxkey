"""Short notification sounds.

The whole reason this module has a ``child_environment`` function: ``pw-play``
parses ``--volume`` with ``strtof``, which honours ``LC_NUMERIC``. On a machine
using a comma decimal separator, "0.5" stops at the dot and becomes zero, so
the sound plays at silence. Any float handed to a C binary as an argument needs
the same treatment.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from voxkey import state

logger = logging.getLogger(__name__)

SOUND_COMPLETE = Path("/usr/share/sounds/freedesktop/stereo/message.oga")
SOUND_BELL = Path("/usr/share/sounds/freedesktop/stereo/dialog-warning.oga")

VOLUME = "0.5"
PLAYERS = ("pw-play", "paplay", "canberra-gtk-play")

Spawner = Callable[[list[str], dict[str, str]], None]


def build_command(player: str, path: Path) -> list[str]:
    if player == "pw-play":
        return [player, f"--volume={VOLUME}", str(path)]
    if player == "canberra-gtk-play":
        return [player, "-f", str(path)]
    return [player, str(path)]


def child_environment(base: Mapping[str, str]) -> dict[str, str]:
    """The child's environment, with the numeric locale forced to C."""
    return {**base, "LC_NUMERIC": "C"}


def _spawn(command: list[str], environment: dict[str, str]) -> None:
    subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def play(path: Path, spawner: Spawner | None = None) -> bool:
    """Play a sound unless muted or missing. Returns whether a player started."""
    if not state.sound_enabled() or not path.exists():
        return False
    launch = spawner if spawner is not None else _spawn
    environment = child_environment(os.environ)
    for player in PLAYERS:
        try:
            launch(build_command(player, path), environment)
        except FileNotFoundError:
            continue
        else:
            return True
    logger.warning("no audio player available, tried %s", ", ".join(PLAYERS))
    return False
