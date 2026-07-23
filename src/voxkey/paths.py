"""Every filesystem location voxkey uses.

This is the single source of truth for paths. No other module calls
``expanduser`` or reads an XDG variable, so redirecting the whole application
into a temporary directory is one fixture away.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "voxkey"
LEGACY_APP_NAME = "dictate"

#: Directory a project may carry to add its own vocabulary, relative to cwd.
PROJECT_HINTS_DIRNAME = ".voxkey-hints.d"
LEGACY_PROJECT_HINTS_DIRNAME = ".dictate-hints.d"


def _xdg_base(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable)
    if value:
        return Path(value)
    return Path("~").expanduser() / fallback


def config_dir() -> Path:
    return _xdg_base("XDG_CONFIG_HOME", ".config") / APP_NAME


def data_dir() -> Path:
    return _xdg_base("XDG_DATA_HOME", ".local/share") / APP_NAME


# The two legacy_* helpers locate an existing dictate installation. They are the
# hooks for the first-run migration (copy dictate's config, hints and state into
# voxkey's directories) specified for the packaging plan; nothing consumes them
# until that migration lands. Kept here so the migration has one place to read
# from, alongside the already-wired LEGACY_PROJECT_HINTS_DIRNAME.
def legacy_config_dir() -> Path:
    return _xdg_base("XDG_CONFIG_HOME", ".config") / LEGACY_APP_NAME


def legacy_data_dir() -> Path:
    return _xdg_base("XDG_DATA_HOME", ".local/share") / LEGACY_APP_NAME


def config_file() -> Path:
    return config_dir() / "config.toml"


def hints_dir() -> Path:
    return config_dir() / "hints.d"


def socket_file() -> Path:
    return data_dir() / "voxkey.sock"


def pid_file() -> Path:
    return data_dir() / "voxkey.pid"


def language_file() -> Path:
    return data_dir() / "language"


def state_file() -> Path:
    return data_dir() / "state"


def sound_file() -> Path:
    return data_dir() / "sound"


def stop_file() -> Path:
    return data_dir() / "stop"
