from __future__ import annotations

import pytest
from evdev import ecodes

from voxkey.ptt.keyboard import NoKeyboardError, _read_key_events

KEY = ecodes.KEY_A


class FakeSelectorKey:
    def __init__(self, fd: int) -> None:
        self.fd = fd


class FakeSelector:
    """Returns scripted ready-batches; records unregistered fds."""

    def __init__(self, batches: list[list[int]]) -> None:
        self._batches = list(batches)
        self.unregistered: list[int] = []

    def select(self):
        if not self._batches:
            # No further readiness scripted: the real selector would block, but
            # the tests never pull more events than they scripted.
            raise AssertionError("select() called more often than scripted")
        return [(FakeSelectorKey(fd), None) for fd in self._batches.pop(0)]

    def unregister(self, fd: int) -> None:
        self.unregistered.append(fd)


class FakeEvent:
    def __init__(self, code: int, value: int) -> None:
        self.type = ecodes.EV_KEY
        self.code = code
        self.value = value

    def timestamp(self) -> float:
        return 1.0


class FakeDevice:
    def __init__(self, events=None, error: Exception | None = None) -> None:
        self._events = events or []
        self._error = error
        self.closed = False

    def read(self):
        if self._error is not None:
            raise self._error
        return list(self._events)

    def close(self) -> None:
        self.closed = True


def test_one_device_unplugging_does_not_stop_the_others() -> None:
    dead = FakeDevice(error=OSError("[Errno 19] No such device"))
    alive = FakeDevice(events=[FakeEvent(KEY, 1)])
    devices = {1: dead, 2: alive}
    selector = FakeSelector([[1, 2]])  # both ready in the same batch

    events = _read_key_events(selector, devices, KEY)
    first = next(events)

    assert first.pressed is True  # the surviving keyboard still yields
    assert 1 in selector.unregistered  # the dead one was dropped
    assert dead.closed is True
    assert 1 not in devices and 2 in devices


def test_last_device_disconnecting_raises_no_keyboard() -> None:
    dead = FakeDevice(error=OSError("[Errno 19] No such device"))
    devices = {1: dead}
    selector = FakeSelector([[1]])

    with pytest.raises(NoKeyboardError, match="disconnected"):
        next(_read_key_events(selector, devices, KEY))


def test_events_for_other_keys_are_ignored() -> None:
    other = FakeDevice(events=[FakeEvent(ecodes.KEY_B, 1), FakeEvent(KEY, 0)])
    devices = {1: other}
    selector = FakeSelector([[1]])

    first = next(_read_key_events(selector, devices, KEY))
    assert first.pressed is False  # the KEY release, not the KEY_B press
