"""The Settings tab: edit the config by mouse, then write it back.

The form gathers values and hands them to ``model.write_settings``, which
validates and writes the TOML file, then restarts only the units that a change
requires. No validation logic lives here; the model owns it.
"""

from __future__ import annotations

import threading

from gi.repository import GLib, Gtk

from voxkey import paths, service, state
from voxkey.config import ConfigError, load
from voxkey.gui.model import (
    AUTO_MODEL,
    MODELS,
    key_name_from_code,
    units_to_restart,
    write_settings,
)
from voxkey.i18n import _
from voxkey.languages import language_name
from voxkey.output import sound
from voxkey.ptt.keyboard import resolve_key

SECONDS_MIN = 0.1
SECONDS_MAX = 60.0
SECONDS_STEP = 0.1


class SettingsPage:
    """The settings form; ``widget`` is the root GTK box."""

    def __init__(self) -> None:
        # Read the typed config directly; the widgets below mirror its fields.
        self._config = load()
        self.widget = self._build()

    def _build(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        row = 0

        # Push-to-talk key: an editable entry plus a capture button.
        self._key_entry = Gtk.Entry(text=self._config.key)
        detect = Gtk.Button(label=_("Detect…"))
        detect.connect("clicked", self._on_detect_key)
        key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        key_box.pack_start(self._key_entry, True, True, 0)
        key_box.pack_start(detect, False, False, 0)
        row = self._add_row(grid, row, _("Push-to-talk key"), key_box)

        # Language: a dropdown over the configured languages, shown by name. The
        # FR/EN cycle set (config.languages) is left as is; this picks the active
        # one, and the tray's "cycle language" still switches between them.
        self._lang_combo = Gtk.ComboBoxText()
        self._lang_codes = list(self._config.languages)
        for code in self._lang_codes:
            self._lang_combo.append_text(language_name(code))
        current = state.get_language(self._config)
        self._lang_combo.set_active(
            self._lang_codes.index(current) if current in self._lang_codes else 0
        )
        row = self._add_row(grid, row, _("Language"), self._lang_combo)

        # Model: a menu; "auto" means unset, the machine decides. A configured
        # model outside the list (a custom name) is appended so it stays visible.
        self._model_combo = Gtk.ComboBoxText()
        options = list(MODELS)
        current_model = self._config.model or AUTO_MODEL
        if current_model not in options:
            options.append(current_model)
        for name in options:
            self._model_combo.append_text(name)
        self._model_combo.set_active(options.index(current_model))
        row = self._add_row(grid, row, _("Model"), self._model_combo)

        self._pre_spin = self._spin(self._config.pre_buffer_secs)
        row = self._add_row(grid, row, _("Pre-buffer (s)"), self._pre_spin)
        self._silence_spin = self._spin(self._config.silence_secs)
        row = self._add_row(grid, row, _("Silence (s)"), self._silence_spin)
        self._wait_spin = self._spin(self._config.wait_secs)
        row = self._add_row(grid, row, _("Wait (s)"), self._wait_spin)

        # End sound: a runtime state file, not a config key, plus a test button.
        self._sound_check = Gtk.CheckButton(label=_("End-of-dictation sound"))
        self._sound_check.set_active(state.sound_enabled())
        test = Gtk.Button(label=_("Test"))
        test.connect("clicked", self._on_test_sound)
        sound_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sound_box.pack_start(self._sound_check, False, False, 0)
        sound_box.pack_start(test, False, False, 0)
        row = self._add_row(grid, row, _("Sound"), sound_box)

        self._log_check = Gtk.CheckButton(label=_("Log transcribed text"))
        self._log_check.set_active(self._config.log_transcripts)
        row = self._add_row(grid, row, _("Logging"), self._log_check)

        box.pack_start(grid, False, False, 0)

        save = Gtk.Button(label=_("Save"))
        save.connect("clicked", self._on_save)
        box.pack_start(save, False, False, 0)

        self._feedback = Gtk.Label(label="", xalign=0.0)
        self._feedback.set_line_wrap(True)
        box.pack_start(self._feedback, False, False, 0)
        return box

    def _add_row(self, grid: Gtk.Grid, row: int, label: str, widget: Gtk.Widget) -> int:
        grid.attach(Gtk.Label(label=label, xalign=0.0), 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return row + 1

    def _spin(self, value: float) -> Gtk.SpinButton:
        spin = Gtk.SpinButton.new_with_range(SECONDS_MIN, SECONDS_MAX, SECONDS_STEP)
        spin.set_digits(1)
        spin.set_value(value)
        return spin

    # -- actions -----------------------------------------------------------

    def _on_save(self, _button: object) -> None:
        key_text = self._key_entry.get_text().strip()
        try:
            resolve_key(key_text)
        except ValueError as error:
            self._feedback.set_text(str(error))
            return

        index = self._lang_combo.get_active()
        language_code = self._lang_codes[index if index >= 0 else 0]
        model_text = self._model_combo.get_active_text() or AUTO_MODEL
        updates = {
            "key": key_text,
            "language": language_code,
            "model": None if model_text == AUTO_MODEL else model_text,
            "pre_buffer_secs": self._pre_spin.get_value(),
            "silence_secs": self._silence_spin.get_value(),
            "wait_secs": self._wait_spin.get_value(),
            "log_transcripts": self._log_check.get_active(),
        }
        # The end sound and the live language are state files, applied at once
        # and independent of the config write below.
        state.set_sound_enabled(self._sound_check.get_active())
        state.set_language(language_code)
        try:
            changed = write_settings(paths.config_file(), updates)
        except ConfigError as error:
            self._feedback.set_text(str(error))
            return
        service.restart(units_to_restart(changed))
        self._feedback.set_text(_("Saved."))

    def _on_test_sound(self, _button: object) -> None:
        # Force so the test is audible even while the end sound is muted.
        sound.play(sound.SOUND_COMPLETE, force=True)

    def _on_detect_key(self, _button: object) -> None:
        self._feedback.set_text(_("Press a key…"))
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self) -> None:
        try:
            name = self._read_one_key()
        except Exception as error:  # noqa: BLE001  # surfaced in the label, not a crash
            GLib.idle_add(self._feedback.set_text, str(error))
            return
        GLib.idle_add(self._apply_captured_key, name)

    def _read_one_key(self) -> str:
        import evdev
        from evdev import ecodes

        from voxkey.ptt.keyboard import find_keyboards

        device = evdev.InputDevice(find_keyboards()[0])
        try:
            for event in device.read_loop():
                if event.type == ecodes.EV_KEY and event.value == 1:
                    return key_name_from_code(event.code)
        finally:
            device.close()
        return ""

    def _apply_captured_key(self, name: str) -> None:
        if name:
            self._key_entry.set_text(name)
            self._feedback.set_text(_("Detected: {name}").format(name=name))
