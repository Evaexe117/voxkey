from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from voxkey import i18n


@pytest.fixture(autouse=True)
def _reset_i18n() -> Iterator[None]:
    """Restore the module-global translator after every test.

    i18n.setup rebinds a module-level translator, so a test that loads a
    catalogue would otherwise leak that choice into later tests and make the
    suite order-dependent. Saving and restoring it keeps every test isolated.
    """
    saved = i18n._active
    try:
        yield
    finally:
        i18n._active = saved


@pytest.fixture
def xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect every XDG location into tmp_path.

    Every test that touches the filesystem must request this fixture, so that
    a bug in path resolution cannot reach the developer's real config.
    """
    config = tmp_path / "config"
    data = tmp_path / "data"
    config.mkdir()
    data.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path
