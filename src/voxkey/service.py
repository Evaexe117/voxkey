"""Driving voxkey's systemd user units.

A thin shell over ``systemctl --user``, shared by the tray and the control
window so the unit names live in exactly one place. The command builders are
pure and tested; only ``_run`` and ``is_active`` reach the outside.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence

UNIT_DAEMON = "voxkey.service"
UNIT_PTT = "voxkey-ptt.service"

# Start the daemon before the client that drives it, and stop them in reverse,
# so the push-to-talk client never outlives the socket it needs.
_START_ORDER = (UNIT_DAEMON, UNIT_PTT)
_STOP_ORDER = (UNIT_PTT, UNIT_DAEMON)


def start_command() -> list[str]:
    return ["systemctl", "--user", "start", *_START_ORDER]


def stop_command() -> list[str]:
    return ["systemctl", "--user", "stop", *_STOP_ORDER]


def restart_command(units: Iterable[str]) -> list[str] | None:
    """Restart the given units, daemon first, or ``None`` when the set is empty."""
    wanted = set(units)
    ordered = [unit for unit in _START_ORDER if unit in wanted]
    if not ordered:
        return None
    return ["systemctl", "--user", "restart", *ordered]


def is_active_command() -> list[str]:
    return ["systemctl", "--user", "is-active", "--quiet", UNIT_DAEMON]


def _run(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=False)


def start() -> None:
    _run(start_command())


def stop() -> None:
    _run(stop_command())


def restart(units: Iterable[str]) -> None:
    command = restart_command(units)
    if command is not None:
        _run(command)


def is_active() -> bool:
    return subprocess.run(is_active_command(), check=False).returncode == 0
