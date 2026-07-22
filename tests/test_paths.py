from __future__ import annotations

from pathlib import Path

import pytest

from voxkey import paths


def test_config_dir_follows_xdg_config_home(xdg: Path) -> None:
    assert paths.config_dir() == xdg / "config" / "voxkey"


def test_data_dir_follows_xdg_data_home(xdg: Path) -> None:
    assert paths.data_dir() == xdg / "data" / "voxkey"


def test_config_dir_falls_back_to_home_when_xdg_unset(
    xdg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert paths.config_dir() == xdg / ".config" / "voxkey"


def test_every_file_lives_under_its_directory(xdg: Path) -> None:  # noqa: ARG001
    assert paths.config_file().parent == paths.config_dir()
    assert paths.hints_dir().parent == paths.config_dir()
    for getter in (
        paths.socket_file,
        paths.pid_file,
        paths.language_file,
        paths.state_file,
        paths.sound_file,
        paths.stop_file,
    ):
        assert getter().parent == paths.data_dir(), getter.__name__


def test_legacy_dirs_point_at_dictate(xdg: Path) -> None:
    assert paths.legacy_config_dir() == xdg / "config" / "dictate"
    assert paths.legacy_data_dir() == xdg / "data" / "dictate"
