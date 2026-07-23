from __future__ import annotations

from pathlib import Path

import pytest

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


def test_delivery_chimes_success_when_the_copy_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voxkey.output import clipboard, sound
    from voxkey.ptt.runner import deliver_to_clipboard

    played: list[str] = []
    monkeypatch.setattr(clipboard, "copy", lambda _text: True)
    monkeypatch.setattr(sound, "play", lambda path: played.append(str(path)))
    deliver_to_clipboard("hello")
    assert played == [str(sound.SOUND_COMPLETE)]


def test_delivery_rings_the_bell_when_the_copy_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voxkey.output import clipboard, sound
    from voxkey.ptt.runner import deliver_to_clipboard

    played: list[str] = []
    monkeypatch.setattr(clipboard, "copy", lambda _text: False)
    monkeypatch.setattr(sound, "play", lambda path: played.append(str(path)))
    deliver_to_clipboard("hello")
    assert played == [str(sound.SOUND_BELL)]


def test_daemon_session_reads_the_language_live_each_dictation(
    xdg: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # voxkey lang must take effect on the next hold, not be frozen at start.
    from voxkey import hints, paths, state
    from voxkey.config import Config
    from voxkey.ipc.protocol import DictationRequest
    from voxkey.ptt import runner

    sent: list[str] = []

    def fake_dictate(
        _sock: object, request: DictationRequest, _on_status: object = None
    ) -> str:
        sent.append(request.language)
        return "x"

    monkeypatch.setattr(runner, "dictate_once", fake_dictate)
    monkeypatch.setattr(hints, "load_hints", lambda: None)
    session = runner.DaemonSession(paths.socket_file(), Config(language="en"))
    session.start()
    session.finish()
    state.set_language("fr")
    session.start()
    session.finish()
    assert sent == ["en", "fr"]
