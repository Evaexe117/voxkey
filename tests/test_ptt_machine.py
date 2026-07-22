from __future__ import annotations

from voxkey.ptt.machine import MIN_HOLD_SECS, HoldDecision, HoldMachine, KeyEvent


def test_a_genuine_dictation_is_accepted() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    assert machine.feed(KeyEvent(pressed=True, timestamp=0.0)) is HoldDecision.START
    assert machine.feed(KeyEvent(pressed=False, timestamp=2.0)) is HoldDecision.ACCEPT


def test_a_phantom_press_is_discarded() -> None:
    # RIGHTCTRL is also the paste modifier, so every Ctrl+V retriggers a
    # recording. Measured: every press under 0.6 s was a phantom, and the
    # shortest genuine dictation was 2.0 s.
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=0.4)) is HoldDecision.DISCARD


def test_the_boundary_is_inclusive() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=1.0)) is HoldDecision.ACCEPT


def test_a_repeat_while_already_held_is_ignored() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=True, timestamp=0.5)) is HoldDecision.IGNORE


def test_a_release_without_a_press_is_ignored() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    assert machine.feed(KeyEvent(pressed=False, timestamp=1.0)) is HoldDecision.IGNORE


def test_holding_reflects_the_current_state() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    assert machine.holding is False
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.holding is True
    machine.feed(KeyEvent(pressed=False, timestamp=2.0))
    assert machine.holding is False


def test_a_phantom_then_a_genuine_press_both_behave() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=0.2)) is HoldDecision.DISCARD
    machine.feed(KeyEvent(pressed=True, timestamp=5.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=8.0)) is HoldDecision.ACCEPT


def test_the_default_minimum_hold_is_one_second() -> None:
    assert MIN_HOLD_SECS == 1.0
