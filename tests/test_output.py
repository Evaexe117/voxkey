from __future__ import annotations

import os
from pathlib import Path

import pytest

from voxkey import state
from voxkey.output import clipboard, sound


def test_clipboard_uses_xsel_not_wl_copy() -> None:
    # wtype does not work under GNOME Wayland, and xsel is focus independent.
    assert clipboard.CLIPBOARD_COMMAND[0] == "xsel"


def test_clipboard_sends_the_text_on_stdin() -> None:
    seen: list[tuple[list[str], bytes]] = []

    def runner(command: list[str], payload: bytes) -> int:
        seen.append((command, payload))
        return 0

    assert clipboard.copy("hello", runner=runner) is True
    assert seen[0][1] == b"hello"


def test_clipboard_reports_failure() -> None:
    assert clipboard.copy("hello", runner=lambda command, payload: 1) is False  # noqa: ARG005


def test_sound_command_carries_the_volume() -> None:
    command = sound.build_command("pw-play", Path("/tmp/a.oga"))
    assert command == ["pw-play", f"--volume={sound.VOLUME}", "/tmp/a.oga"]


def test_players_without_a_volume_flag_get_a_bare_command() -> None:
    assert sound.build_command("paplay", Path("/tmp/a.oga")) == ["paplay", "/tmp/a.oga"]


def test_child_environment_forces_the_c_numeric_locale() -> None:
    # pw-play parses --volume with strtof, which honours LC_NUMERIC. Under a
    # comma-decimal locale "0.5" stops at the dot and becomes zero, i.e.
    # silence. Any float handed to a C binary as an argument needs this.
    environment = sound.child_environment({"LC_NUMERIC": "fr_FR.UTF-8", "HOME": "/h"})
    assert environment["LC_NUMERIC"] == "C"
    assert environment["HOME"] == "/h"


def test_child_environment_sets_the_locale_even_when_it_was_unset() -> None:
    assert sound.child_environment({})["LC_NUMERIC"] == "C"


def test_play_is_silent_when_the_tray_muted_it(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    state.set_sound_enabled(False)
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    spawned: list[list[str]] = []
    assert sound.play(target, spawner=lambda c, _: spawned.append(c)) is False
    assert spawned == []


def test_play_forced_ignores_the_mute_for_the_settings_test(
    xdg: Path,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    # The Settings "test" button must be audible even while the end sound is off.
    state.set_sound_enabled(False)
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    spawned: list[list[str]] = []
    result = sound.play(target, spawner=lambda c, _: spawned.append(c), force=True)
    assert result is True
    assert spawned  # a player was launched despite the mute


def test_play_is_silent_when_the_file_is_missing(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    spawned: list[list[str]] = []
    result = sound.play(tmp_path / "absent.oga", spawner=lambda c, _: spawned.append(c))
    assert result is False
    assert spawned == []


def test_play_falls_back_to_the_next_player(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    attempted: list[str] = []

    def spawner(command: list[str], environment: dict[str, str]) -> None:  # noqa: ARG001
        attempted.append(command[0])
        if command[0] != "canberra-gtk-play":
            raise FileNotFoundError(command[0])

    assert sound.play(target, spawner=spawner) is True
    assert attempted == list(sound.PLAYERS)


def test_play_passes_the_forced_locale_to_the_child(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    captured: dict[str, str] = {}

    def spawner(command: list[str], environment: dict[str, str]) -> None:  # noqa: ARG001
        captured.update(environment)

    sound.play(target, spawner=spawner)
    assert captured["LC_NUMERIC"] == "C"
    assert "PATH" in captured or "PATH" not in os.environ


def test_spawn_reaps_finished_players_so_they_do_not_linger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The default spawner must poll previously started players, otherwise a
    # finished sound process stays a zombie for the life of the daemon.
    polled: list[FakePopen] = []

    class FakePopen:
        def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: ARG002
            self._done = False

        def poll(self) -> int | None:
            polled.append(self)
            self._done = True
            return 0 if self._done else None

    monkeypatch.setattr(sound.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(sound, "_live", [])

    sound._spawn(["pw-play", "/tmp/a.oga"], {})
    assert len(sound._live) == 1
    first = sound._live[0]

    sound._spawn(["pw-play", "/tmp/b.oga"], {})
    assert first in polled  # the first child was polled on the second spawn
    assert first not in sound._live  # and dropped once it had finished
    assert len(sound._live) == 1
