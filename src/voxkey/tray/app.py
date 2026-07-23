"""The AyatanaAppIndicator tray icon.

A thin shell: it reads the runtime state, maps it to an icon through the pure
``icons`` module, and drives the daemon through ``service`` and the state
files through ``state``. It holds no logic of its own, matching dictate's tray.
GTK is imported here, never at package import, so ``voxkey serve`` on a headless
box never needs it.
"""

from __future__ import annotations

import logging
import subprocess
import sys

import gi

try:
    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
except ValueError as error:  # namespace missing: report it as an import failure
    raise ImportError(str(error)) from error

from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402

from voxkey import state  # noqa: E402
from voxkey.config import Config, load  # noqa: E402
from voxkey.i18n import _, setup  # noqa: E402
from voxkey.languages import language_name  # noqa: E402
from voxkey.service import is_active, start, stop  # noqa: E402
from voxkey.tray import icons  # noqa: E402

logger = logging.getLogger(__name__)

SERVICE_POLL_MS = 5000
STATE_POLL_MS = 300


class VoxkeyTray:
    """The status icon and its menu."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._active = is_active()
        self._shown = ""

        self._indicator = AppIndicator.Indicator.new_with_path(
            "voxkey-tray",
            icons.ICON_OFF,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            str(icons.assets_dir()),
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        menu = Gtk.Menu()
        self._toggle_item = Gtk.MenuItem()
        self._toggle_item.connect("activate", self._on_toggle_dictation)
        menu.append(self._toggle_item)

        self._sound_item = Gtk.MenuItem()
        self._sound_item.connect("activate", self._on_toggle_sound)
        menu.append(self._sound_item)

        self._language_item = Gtk.MenuItem()
        self._language_item.connect("activate", self._on_cycle_language)
        menu.append(self._language_item)

        menu.append(Gtk.SeparatorMenuItem())

        settings_item = Gtk.MenuItem(label=_("Settings…"))
        settings_item.connect("activate", self._on_open_settings)
        menu.append(settings_item)

        quit_item = Gtk.MenuItem(label=_("Quit the icon"))
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)

        menu.show_all()
        self._indicator.set_menu(menu)

        self._refresh_labels()
        self._refresh_icon()
        GLib.timeout_add(SERVICE_POLL_MS, self._poll_service)
        GLib.timeout_add(STATE_POLL_MS, self._poll_icon)

    # -- menu actions ------------------------------------------------------

    def _on_toggle_dictation(self, _item: object) -> None:
        if is_active():
            stop()
        else:
            state.set_state(state.STATE_IDLE)
            start()
        # Give systemd a moment to change state, then reflect it.
        GLib.timeout_add(800, self._poll_service)

    def _on_toggle_sound(self, _item: object) -> None:
        state.set_sound_enabled(not state.sound_enabled())
        self._refresh_labels()

    def _on_cycle_language(self, _item: object) -> None:
        current = state.get_language(self._config)
        state.set_language(state.next_language(current, self._config.languages))
        self._refresh_labels()

    def _on_open_settings(self, _item: object) -> None:
        # Launch through the running interpreter so it works from a venv where
        # the `voxkey` script may not be on PATH.
        subprocess.Popen([sys.executable, "-m", "voxkey", "gui"])

    def _on_quit(self, _item: object) -> None:
        # Quit the icon only; the daemon keeps running.
        Gtk.main_quit()

    # -- refresh -----------------------------------------------------------

    def _refresh_labels(self) -> None:
        self._active = is_active()
        self._toggle_item.set_label(
            _("Turn dictation off") if self._active else _("Turn dictation on")
        )
        self._sound_item.set_label(
            _("Mute the end sound")
            if state.sound_enabled()
            else _("Unmute the end sound")
        )
        code = state.get_language(self._config)
        self._language_item.set_label(
            _("Language: {name}").format(name=language_name(code))
        )

    def _poll_service(self) -> bool:
        was = self._active
        self._active = is_active()
        if self._active != was:
            self._refresh_labels()
        self._refresh_icon()
        return True

    def _poll_icon(self) -> bool:
        self._refresh_icon()
        return True

    def _refresh_icon(self) -> None:
        current = state.get_state()
        name, tooltip = icons.resolve_icon(current, active=self._active)
        if name != self._shown:
            self._shown = name
            self._indicator.set_icon_full(name, tooltip)
            self._indicator.set_title(tooltip)


def run() -> int:
    """Run the tray icon until it is quit."""
    setup()
    VoxkeyTray(load())
    Gtk.main()
    return 0
