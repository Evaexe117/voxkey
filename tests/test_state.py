from __future__ import annotations

from pathlib import Path

from voxkey import paths, state
from voxkey.config import Config


def test_write_atomic_creates_parent_directories(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    target = tmp_path / "deep" / "deeper" / "file"
    state.write_atomic(target, "value")
    assert target.read_text() == "value"


def test_write_atomic_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "file"
    state.write_atomic(target, "value")
    assert [p.name for p in tmp_path.iterdir()] == ["file"]


def test_write_atomic_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "file"
    state.write_atomic(target, "first")
    state.write_atomic(target, "second")
    assert target.read_text() == "second"


def test_read_text_returns_the_default_when_absent(tmp_path: Path) -> None:
    assert state.read_text(tmp_path / "nothing", default="fallback") == "fallback"


def test_language_falls_back_to_the_configured_one(xdg: Path) -> None:  # noqa: ARG001
    assert state.get_language(Config(language="fr")) == "fr"


def test_language_file_wins_over_the_configuration(xdg: Path) -> None:  # noqa: ARG001
    state.set_language("es")
    assert state.get_language(Config(language="fr")) == "es"
    assert paths.language_file().read_text().strip() == "es"


def test_blank_language_file_is_ignored(xdg: Path) -> None:  # noqa: ARG001
    state.write_atomic(paths.language_file(), "   ")
    assert state.get_language(Config(language="fr")) == "fr"


def test_next_language_cycles_and_wraps() -> None:
    assert state.next_language("en", ["en", "fr"]) == "fr"
    assert state.next_language("fr", ["en", "fr"]) == "en"


def test_next_language_of_an_unlisted_code_returns_the_first() -> None:
    assert state.next_language("de", ["en", "fr"]) == "en"


def test_next_language_of_a_single_entry_list_is_itself() -> None:
    assert state.next_language("en", ["en"]) == "en"


def test_sound_is_enabled_unless_explicitly_off(xdg: Path) -> None:  # noqa: ARG001
    assert state.sound_enabled() is True
    state.set_sound_enabled(False)
    assert state.sound_enabled() is False
    state.set_sound_enabled(True)
    assert state.sound_enabled() is True


def test_state_round_trips(xdg: Path) -> None:  # noqa: ARG001
    state.set_state(state.STATE_RECORDING)
    assert state.get_state() == state.STATE_RECORDING
