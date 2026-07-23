"""The Status tab: what voxkey is doing, and three quick actions.

Renders ``model.status_view`` into labels and wires start/stop, dictate once,
and cycle language to the same operations the tray uses. No logic of its own.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import threading

from gi.repository import GLib, Gtk

from voxkey import service, state
from voxkey.audio.devices import choose_input_device, list_input_devices
from voxkey.config import load
from voxkey.gui.model import StatusView, status_view
from voxkey.i18n import _
from voxkey.transcribe.local import detect_cuda, pick_defaults

REFRESH_MS = 2000

# The source strings stay untranslated here: calling _() at module level would
# freeze the untranslated text before setup() runs. They are translated in
# _build, which runs after setup().
_FIELDS = (
    ("daemon", "Daemon"),
    ("model", "Model"),
    ("device", "Device"),
    ("microphone", "Microphone"),
    ("language", "Language"),
    ("key", "Push-to-talk key"),
)


class StatusPage:
    """A tab showing live status; ``widget`` is the root GTK box."""

    def __init__(self) -> None:
        # Probing CUDA imports ctranslate2; do it once, not on every refresh.
        self._has_cuda = detect_cuda()
        self._values: dict[str, Gtk.Label] = {}
        self.widget = self._build()
        self._refresh()
        GLib.timeout_add(REFRESH_MS, self._tick)

    def _build(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        for row, (field, label) in enumerate(_FIELDS):
            name = Gtk.Label(label=f"{_(label)}:", xalign=0.0)
            value = Gtk.Label(label="", xalign=0.0)
            value.set_selectable(True)
            grid.attach(name, 0, row, 1, 1)
            grid.attach(value, 1, row, 1, 1)
            self._values[field] = value
        box.pack_start(grid, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._toggle_button = Gtk.Button()
        self._toggle_button.connect("clicked", self._on_toggle)
        buttons.pack_start(self._toggle_button, False, False, 0)

        once_button = Gtk.Button(label=_("Dictate once"))
        once_button.connect("clicked", self._on_dictate_once)
        buttons.pack_start(once_button, False, False, 0)

        language_button = Gtk.Button(label=_("Cycle language"))
        language_button.connect("clicked", self._on_cycle_language)
        buttons.pack_start(language_button, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self._once_label = Gtk.Label(label="", xalign=0.0)
        self._once_label.set_line_wrap(True)
        box.pack_start(self._once_label, False, False, 0)
        return box

    # -- data --------------------------------------------------------------

    def _compute(self) -> StatusView:
        config = load()
        choice = pick_defaults(has_cuda=self._has_cuda)
        if config.model:
            choice = dataclasses.replace(choice, name=config.model)
        return status_view(
            active=service.is_active(),
            model_name=choice.name,
            device=choice.device,
            compute_type=choice.compute_type,
            microphone=self._microphone(),
            language_code=state.get_language(config),
            key=config.key,
        )

    def _microphone(self) -> str | None:
        try:
            devices = list_input_devices()
        except Exception:  # noqa: BLE001  # no sound card is a display detail, not a crash
            return None
        index = choose_input_device(devices)
        return next((d.name for d in devices if d.index == index), None)

    def _refresh(self) -> None:
        view = self._compute()
        for field, _label in _FIELDS:
            self._values[field].set_text(getattr(view, field))
        self._toggle_button.set_label(
            _("Turn off") if service.is_active() else _("Turn on")
        )

    def _tick(self) -> bool:
        self._refresh()
        return True

    # -- actions -----------------------------------------------------------

    def _on_toggle(self, _button: object) -> None:
        if service.is_active():
            service.stop()
        else:
            state.set_state(state.STATE_IDLE)
            service.start()
        GLib.timeout_add(800, self._tick)

    def _on_cycle_language(self, _button: object) -> None:
        config = load()
        current = state.get_language(config)
        state.set_language(state.next_language(current, config.languages))
        self._refresh()

    def _on_dictate_once(self, _button: object) -> None:
        self._once_label.set_text(_("Dictating…"))
        threading.Thread(target=self._dictate_once_worker, daemon=True).start()

    def _dictate_once_worker(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "voxkey", "once"],
            capture_output=True,
            text=True,
            check=False,
        )
        text = (
            result.stdout.strip()
            if result.returncode == 0
            else (result.stderr.strip() or _("No speech detected"))
        )
        GLib.idle_add(self._once_label.set_text, text)
