from __future__ import annotations

from pathlib import Path

import pytest

from voxkey.config import ConfigError, load
from voxkey.gui import model
from voxkey.ptt.keyboard import resolve_key


def test_write_creates_the_file_with_only_the_edited_key(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    changed = model.write_settings(path, {"key": "PAUSE"})
    assert path.exists()
    assert load(path).key == "PAUSE"
    assert changed == {"key"}
    assert "silence_secs" not in path.read_text()  # untouched keys not written


def test_write_keeps_comments_and_untouched_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "# my notes\n"
        'key = "RIGHTCTRL"  # the push to talk key\n'
        "silence_secs = 2.5\n"
    )
    changed = model.write_settings(path, {"silence_secs": 4.0})
    text = path.read_text()
    assert "# my notes" in text  # standalone comment kept
    assert "# the push to talk key" in text  # untouched key's inline comment kept
    assert 'key = "RIGHTCTRL"' in text  # untouched key kept
    assert load(path).silence_secs == 4.0
    assert changed == {"silence_secs"}


def test_write_reports_no_change_when_the_value_is_identical(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('key = "RIGHTCTRL"\n')
    assert model.write_settings(path, {"key": "RIGHTCTRL"}) == set()


def test_invalid_value_raises_and_leaves_the_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "silence_secs = 3.0\n"
    path.write_text(original)
    with pytest.raises(ConfigError, match="silence_secs"):
        model.write_settings(path, {"silence_secs": -1.0})
    assert path.read_text() == original  # nothing written


def test_auto_model_removes_the_key(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model = "small"\n')
    changed = model.write_settings(path, {"model": None})
    assert "model" not in path.read_text()
    assert load(path).model is None
    assert changed == {"model"}


def test_languages_list_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    changed = model.write_settings(path, {"languages": ["fr", "en", "de"]})
    assert load(path).languages == ("fr", "en", "de")
    assert changed == {"languages"}


def test_units_to_restart_maps_keys_to_units() -> None:
    assert model.units_to_restart({"key"}) == {model.UNIT_PTT}
    assert model.units_to_restart({"model"}) == {model.UNIT_DAEMON}
    assert model.units_to_restart({"silence_secs"}) == {model.UNIT_DAEMON}
    assert model.units_to_restart({"key", "model"}) == {
        model.UNIT_PTT,
        model.UNIT_DAEMON,
    }


def test_language_and_empty_changes_restart_nothing() -> None:
    assert model.units_to_restart({"languages"}) == set()
    assert model.units_to_restart(set()) == set()


def test_key_name_round_trips_with_resolve_key() -> None:
    for name in ("RIGHTCTRL", "LEFTCTRL", "CAPSLOCK", "PAUSE", "RIGHTALT"):
        assert model.key_name_from_code(resolve_key(name)) == name


def test_unknown_key_code_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown key code"):
        model.key_name_from_code(999999)


def test_status_view_formats_the_display_strings() -> None:
    view = model.status_view(
        active=True,
        model_name="medium",
        device="cuda",
        compute_type="int8",
        microphone="pipewire",
        language_code="fr",
        key="RIGHTCTRL",
    )
    assert view.device == "CUDA (int8)"
    assert view.model == "medium"
    assert view.microphone == "pipewire"
    assert "fr" in view.language
    assert view.key == "RIGHTCTRL"
    assert view.daemon  # non-empty running label


def test_status_view_stopped_and_without_a_microphone() -> None:
    stopped = model.status_view(
        active=False,
        model_name="small",
        device="cpu",
        compute_type="int8",
        microphone=None,
        language_code="en",
        key="PAUSE",
    )
    running = model.status_view(
        active=True,
        model_name="small",
        device="cpu",
        compute_type="int8",
        microphone=None,
        language_code="en",
        key="PAUSE",
    )
    assert stopped.daemon != running.daemon
    assert stopped.microphone  # a "none found" label, never empty
