"""Reading the keyboard through evdev.

This module is a thin shell around a device that a test cannot open. Every
decision it might have made lives in ``machine`` instead.

Reading /dev/input/event* requires membership of the ``input`` group. The
desktop session does not carry that group, which is why the systemd unit wraps
the command in ``sg input -c``. Without the wrapper this exits immediately with
"no keyboard found".
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from voxkey.ppt.machine import KeyEvent

logger = logging.getLogger(__name__)


class NoKeyboardError(RuntimeError):
    """No readable keyboard was found. Usually the missing input group."""


def resolve_key(name: str) -> int:
    """Turn a key name without its KEY_ prefix into an evdev code."""
    from evdev import ecodes

    code = getattr(ecodes, f"KEY_{name.upper()}", None)
    if code is None:
        raise ValueError(f"unknown key name: {name}")
    return int(code)


def find_keyboards() -> list[str]:
    """Device paths that look like a real keyboard."""
    import evdev
    from evdev import ecodes

    found: list[str] = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        capabilities = device.capabilities()
        keys = capabilities.get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys and ecodes.KEY_ENTER in keys:
            found.append(path)
    if not found:
        raise NoKeyboardError(
            "no keyboard found. Check membership of the input group, and that "
            "the service runs through the sg input wrapper."
        )
    return found


def key_events(device_path: str, key_code: int) -> Iterator[KeyEvent]:
    """Yield press and release events for one key on one device."""
    import evdev
    from evdev import ecodes

    device = evdev.InputDevice(device_path)
    for event in device.read_loop():
        if event.type != ecodes.EV_KEY or event.code != key_code:
            continue
        if event.value == 1:
            yield KeyEvent(pressed=True, timestamp=event.timestamp())
        elif event.value == 0:
            yield KeyEvent(pressed=False, timestamp=event.timestamp())
