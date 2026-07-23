"""Mapping the runtime state to a tray icon and tooltip. Pure, no GTK.

Colours: grey crossed means stopped, white means ready, red means recording is
under way, green means the text landed on the clipboard, orange means nothing
was transcribed. ``transcribing`` reuses the idle icon, so the icon changes on
recording and on a result, not on every internal phase.
"""

from __future__ import annotations

from pathlib import Path

from voxkey import state
from voxkey.i18n import _

ICON_OFF = "voxkey-off"
ICON_IDLE = "voxkey-idle"
ICON_RECORDING = "voxkey-recording"
ICON_DONE = "voxkey-done"
ICON_ERROR = "voxkey-error"


def assets_dir() -> Path:
    """The directory holding the SVG icons, resolved next to this module."""
    return Path(__file__).resolve().parent / "assets"


def resolve_icon(current: str, *, active: bool) -> tuple[str, str]:
    """The icon basename and tooltip for a state.

    A stopped daemon is always ``off`` regardless of the last written state.
    An unrecognised state falls back to idle rather than showing nothing.
    """
    if not active:
        return ICON_OFF, _("Dictation stopped")
    table: dict[str, tuple[str, str]] = {
        state.STATE_IDLE: (ICON_IDLE, _("Ready, hold the key to speak")),
        state.STATE_RECORDING: (ICON_RECORDING, _("Recording…")),
        state.STATE_TRANSCRIBING: (ICON_IDLE, _("Transcribing…")),
        state.STATE_DONE: (ICON_DONE, _("Text copied to the clipboard")),
        state.STATE_ERROR: (ICON_ERROR, _("Nothing transcribed (error or silence)")),
        state.STATE_OFF: (ICON_OFF, _("Dictation stopped")),
    }
    return table.get(current, table[state.STATE_IDLE])
