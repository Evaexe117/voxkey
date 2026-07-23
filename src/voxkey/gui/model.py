"""Pure logic behind the control window and the tray.

No GTK here. Everything the window and the tray decide is computed in this
module and tested directly, so the widget code stays a thin shell that only
wires signals. The rule from the parent design holds: code that touches the
display carries no logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import tomlkit

from voxkey import state
from voxkey.config import parse
from voxkey.i18n import _
from voxkey.languages import language_name

# Re-exported (alias form) so callers can name the units through the model.
from voxkey.service import UNIT_DAEMON as UNIT_DAEMON
from voxkey.service import UNIT_PTT as UNIT_PTT

#: Models the Settings tab offers. ``auto`` means "let the machine decide",
#: which is ``config.model`` unset.
AUTO_MODEL = "auto"
MODELS: tuple[str, ...] = (AUTO_MODEL, "tiny", "base", "small", "medium", "large-v3")

# Which config key, once changed, needs which unit restarted. Keys in neither
# set (``languages``, and the sound toggle, which is not a config key) take
# effect live through the state files and restart nothing.
_PTT_KEYS = frozenset({"key"})
_DAEMON_KEYS = frozenset(
    {
        "model",
        "pre_buffer_secs",
        "silence_secs",
        "wait_secs",
        "log_transcripts",
        "remote",
    }
)


@dataclass(frozen=True)
class StatusView:
    """The read-only strings the Status tab shows."""

    daemon: str
    model: str
    device: str
    microphone: str
    language: str
    key: str


def status_view(
    *,
    active: bool,
    model_name: str,
    device: str,
    compute_type: str,
    microphone: str | None,
    language_code: str,
    key: str,
) -> StatusView:
    """Assemble the Status view-model. Pure over its arguments."""
    return StatusView(
        daemon=_("Running") if active else _("Stopped"),
        model=model_name,
        device=f"{device.upper()} ({compute_type})",
        microphone=microphone if microphone else _("none found"),
        language=f"{language_name(language_code)} ({language_code})",
        key=key,
    )


def units_to_restart(changed: Iterable[str]) -> set[str]:
    """The systemd units to restart, given which config keys changed."""
    keys = set(changed)
    units: set[str] = set()
    if keys & _PTT_KEYS:
        units.add(UNIT_PTT)
    if keys & _DAEMON_KEYS:
        units.add(UNIT_DAEMON)
    return units


def key_name_from_code(code: int) -> str:
    """The bare key name voxkey stores for an evdev code.

    The inverse of ``keyboard.resolve_key``: code 97 becomes ``"RIGHTCTRL"``.
    Raises ``ValueError`` for a code no key maps to, matching ``resolve_key``.
    """
    from evdev import ecodes

    names = ecodes.KEY.get(code)
    if names is None:
        raise ValueError(f"unknown key code: {code}")
    name = names[0] if isinstance(names, list) else names
    return str(name).removeprefix("KEY_")


def _document(path: Path) -> tomlkit.TOMLDocument:
    try:
        return tomlkit.parse(path.read_text())
    except FileNotFoundError:
        return tomlkit.document()


def _apply(document: tomlkit.TOMLDocument, updates: Mapping[str, object]) -> None:
    for key, value in updates.items():
        if key == "model" and value is None:
            # "auto" means the key is absent, so the machine default applies.
            document.pop("model", None)
        elif isinstance(value, (list, tuple)):
            document[key] = list(value)
        else:
            document[key] = value


def write_settings(path: Path, updates: Mapping[str, object]) -> set[str]:
    """Apply ``updates`` to ``config.toml``, validate, then write it back.

    The write goes through tomlkit, so comments and key order in the file
    survive. The merged result is validated through ``config.parse`` first, and
    an invalid value raises ``ConfigError`` before anything is written, so a bad
    entry in the form never corrupts the file. Returns the set of keys whose
    effective value actually changed, which drives ``units_to_restart``.
    """
    document = _document(path)
    before = parse(document.unwrap())
    _apply(document, updates)
    after = parse(document.unwrap())  # validates the result; may raise
    state.write_atomic(path, tomlkit.dumps(document))
    return {
        field
        for field in updates
        if getattr(before, field) != getattr(after, field)
    }
