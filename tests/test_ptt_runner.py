from __future__ import annotations

from voxkey.ptt.machine import KeyEvent
from voxkey.ptt.runner import FakeSession, run_push_to_talk


def test_a_genuine_hold_delivers_the_text() -> None:
    session = FakeSession(["hello there"])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(False, 2.0)], session, delivered.append
    )
    assert delivered == ["hello there"]
    assert session.log == ["start", "finish"]


def test_a_phantom_press_aborts_and_delivers_nothing() -> None:
    session = FakeSession(["subtitle boilerplate"])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(False, 0.3)], session, delivered.append
    )
    assert delivered == []
    assert session.log == ["start", "abort"]


def test_empty_text_is_not_delivered() -> None:
    session = FakeSession([""])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(False, 2.0)], session, delivered.append
    )
    assert delivered == []


def test_two_holds_deliver_twice() -> None:
    session = FakeSession(["first", "second"])
    delivered: list[str] = []
    run_push_to_talk(
        [
            KeyEvent(True, 0.0),
            KeyEvent(False, 2.0),
            KeyEvent(True, 5.0),
            KeyEvent(False, 8.0),
        ],
        session,
        delivered.append,
    )
    assert delivered == ["first", "second"]


def test_a_repeat_event_does_not_start_a_second_session() -> None:
    session = FakeSession(["once"])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(True, 0.5), KeyEvent(False, 2.0)],
        session,
        delivered.append,
    )
    assert session.log == ["start", "finish"]
    assert delivered == ["once"]


def test_a_failing_session_does_not_stop_the_loop() -> None:
    session = FakeSession(["ok"], fail_first=True)
    delivered: list[str] = []
    run_push_to_talk(
        [
            KeyEvent(True, 0.0),
            KeyEvent(False, 2.0),
            KeyEvent(True, 5.0),
            KeyEvent(False, 8.0),
        ],
        session,
        delivered.append,
    )
    assert delivered == ["ok"]
