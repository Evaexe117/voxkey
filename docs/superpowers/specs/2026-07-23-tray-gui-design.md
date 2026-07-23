# voxkey tray and control window - design

This is a follow-on to `2026-07-22-voxkey-design.md`, which already specified a
tray icon (section 5, `tray/app.py`) and a four-tab control window (section 8).
Neither was implemented. This document scopes and details the **first
implementation lot**: the tray icon and a two-tab window (Status, Settings),
plus the systemd user units the tray needs to start and stop the daemon.

The parent design is authoritative for anything not restated here. Where this
document decides something the parent left open, it says so.

## 1. Goal

Give voxkey the desktop surface dictate had, and more:

- a permanent status icon in the system tray, with a menu for the daily
  gestures (turn dictation on or off, mute the end sound, cycle the language);
- a window for configuration by mouse: the push-to-talk key, the language list,
  the model, the three timing thresholds, the end sound, and transcript
  logging, written back to `config.toml`.

The window and the tray hold **no business logic**. They drive the daemon
through the same systemd units and the same state files every other client
uses, and they edit the same TOML file. Two sources of truth would diverge.

## 2. Scope

**In this lot**

- `voxkey tray` - the status icon and its menu.
- `voxkey gui` - the control window, Status and Settings tabs only.
- `packaging/systemd/voxkey.service` and `voxkey-ptt.service`, installed by
  `packaging/install.sh`, so the tray can start and stop the daemon the way
  dictate did with `systemctl --user`.
- The optional extra `voxkey[gui]`, pulling PyGObject and tomlkit.

**Deferred to a later lot** (stated so the auditor does not read their absence
as an omission)

- The Vocabulary and Journal tabs.
- Making the microphone selectable. It is not a `config` key today; adding one
  touches the audio engine, not just the interface. Shown read-only for now.
- First-run migration from dictate (`~/.config/dictate` → `~/.config/voxkey`).
  The `legacy_*` path helpers already exist for it; nothing in this lot uses
  them.
- The headless `voxkey-server.service`. A desktop does not need it.

**Explicitly out of scope**

- Editing `remote` from the window. It stays a hand-edited key in the TOML
  file. The window preserves it on write but offers no control for it.

## 3. Dependencies and packaging

PyGObject (GTK 3) and tomlkit are **optional**, gated behind the `gui` extra:

```
[project.optional-dependencies]
gui = ["PyGObject", "tomlkit"]
```

A headless GPU box running `voxkey serve --listen` must not need GTK, so the
core install stays as it is. `voxkey tray` and `voxkey gui` import GTK lazily,
inside the command handler, and fail with a one-line message naming the extra
when it is missing, never a traceback.

tomlkit is what makes "write the config back with comments preserved" honest.
`tomllib` is read-only; regenerating the file from the dataclass would erase any
comment the user or a future migration wrote. tomlkit round-trips.

The tray needs `AyatanaAppIndicator3` (namespace `0.1`), confirmed present on
the target machine, along with GTK 3 and, on the desktop side, the Cinnamon
StatusNotifier watcher (`xapp-sn-watcher`) that renders the icon. These are
system packages, not pip dependencies; `install.sh` checks for them and prints
what to apt-install if they are missing, rather than letting the import fail
cryptically.

## 4. CLI additions

Two subcommands, matching the parent design's surface:

```
voxkey gui                            open the control window
voxkey tray                           run the tray icon
```

`cli.py` only parses and dispatches, as today. Each handler imports its GTK
module lazily and translates a missing-GTK `ImportError` into a clean message.

## 5. Components

The rule from the parent design holds: **code that touches the display is a
thin shell over pure logic**. The GTK modules wire widgets; every decision they
render lives in `gui/model.py`, which imports no GTK and is tested directly.

**`gui/model.py`** - pure, no GTK, no systemd. Four responsibilities:

- `status_view(config, *, active, device_label, mic_label, language)` builds the
  read-only view-model shown by the Status tab (strings only). Pure over its
  arguments.
- `write_settings(path, updates)` loads the existing `config.toml` with tomlkit
  (or an empty document if absent), applies `updates`, **validates the result
  through the existing `config.parse`**, and only then writes it back
  atomically (temp file then rename, as `state.write_atomic` already does).
  Invalid input raises `ConfigError` and nothing is written. Comments and
  key order in the file survive. Returns the set of keys whose value changed.
- `units_to_restart(changed_keys)` maps the changed keys to the systemd units
  that must restart: `key` → `voxkey-ptt`; `model`, the three `*_secs`,
  `log_transcripts`, `remote` → `voxkey`; `language`, sound → neither (they are
  live through state files). Pure; a table and a set operation.
- `key_name_from_code(code)` reverses an evdev key code to the bare name voxkey
  stores (`RIGHTCTRL`), the inverse of `keyboard.resolve_key`. Pure over the
  `ecodes` table.

**`gui/app.py`** - the `Gtk.Window` with a `Gtk.Notebook` of two pages. Owns no
logic beyond wiring signals to `model.py` and `systemd.py` calls. Opened by
`voxkey gui` and by the tray's Settings item.

**`gui/page_status.py`** - renders `status_view(...)` into labels and wires the
three action buttons (start/stop, dictate once, cycle language) to the same
operations the tray uses.

**`gui/page_settings.py`** - the form. Widgets for each editable key, a
"Détecter…" button for the push-to-talk key, a "Tester" button for the end
sound, and a Save button. On save it calls `write_settings`, then restarts the
units named by `units_to_restart`, and reports the outcome inline.

**`tray/app.py`** - the `AyatanaAppIndicator3` icon. Reads `state`, `sound` and
daemon-active, polls the state file every 300 ms and the service every 5 s, and
maps state to an icon through a pure helper. Its menu items shell out to the
same systemd and state operations. No business logic, matching dictate's tray.

**`tray/assets/`** - four SVG icons (`off`, `idle`, `done`, `error`), adapted
from dictate's set. `recording` and `transcribing` reuse the `idle` icon, as in
dictate.

**`gui/systemd.py`** (thin shell, shared by tray and window) - `start()`,
`stop()`, `restart(units)`, `is_active()`, each a single `systemctl --user`
subprocess call. Isolated here so the callers stay declarative and so this one
file is the only place that knows the unit names.

## 6. Tray behaviour

Icon states and colours are dictate's, preserved:

| State | Icon | Meaning |
|---|---|---|
| off | grey, crossed | dictation stopped |
| idle / recording / transcribing | white | ready, or working |
| done | green | text copied to the clipboard, until the next dictation |
| error | orange | nothing transcribed (error or silence) |

Menu:

- **🎙 Activer / 🔇 Couper la dictée** - starts or stops both units
  (`voxkey` and `voxkey-ptt`). Label and icon follow the actual service state,
  not an assumption.
- **🔔 / 🔕 Son de fin** - toggles the `sound` state file. Live, no restart.
- **🌐 Langue** - cycles through `config.languages` by writing the `language`
  state file. Live, no restart.
- **⚙ Réglages…** - launches `voxkey gui`.
- **Quitter l'icône** - quits the tray only, leaving the daemon running.

The tray reads state; it never computes it. When the daemon is down the icon is
`off` regardless of the last written state, as in dictate.

## 7. Settings semantics

The window edits these existing keys. No new config key is introduced in this
lot.

| Control | Key | Notes |
|---|---|---|
| Push-to-talk key | `key` | "Détecter…" captures the next key press |
| Languages | `languages` | ordered list, cycled by the tray and `lang` |
| Model | `model` | menu: auto (unset) / tiny / base / small / medium / large-v3 |
| Pre-buffer | `pre_buffer_secs` | seconds, > 0 |
| Silence | `silence_secs` | seconds, > 0 |
| Wait | `wait_secs` | seconds, > 0 |
| End sound | (`sound` state file) | on/off, plus a "Tester" button |
| Log transcripts | `log_transcripts` | on/off |

The end sound is a runtime state file, not a config key, so its control writes
the same file the tray toggles; the two stay in sync.

**Key capture.** "Détecter…" reads evdev for the next key-down, resolves its
code to a name with `key_name_from_code`, and shows it. voxkey does not `grab()`
the device, so capturing while `voxkey-ptt` also reads it is safe. A text entry
remains as a fallback for keys the user would rather type; both paths validate
through `keyboard.resolve_key` before Save accepts them. Capture runs on a
worker thread and hands the result back with `GLib.idle_add`, never blocking the
GTK main loop.

**Save.** `write_settings` validates the whole resulting config before writing;
a bad value leaves the file untouched and shows the `ConfigError` message
against the offending field. After a successful write, only the units named by
`units_to_restart(changed)` restart, so a language or sound change never reloads
the model, and changing the model does reload it (seconds, VRAM) as expected.

## 8. systemd units

Two user units under `packaging/systemd/`, mirroring dictate's working pair:

- `voxkey.service` - `ExecStart=voxkey serve`. The resident daemon.
- `voxkey-ptt.service` - the push-to-talk client, `ExecStart` wrapped in
  `sg input -c 'voxkey listen'`, because reading `/dev/input/event*` needs the
  `input` group and a user session does not carry it into the unit. `Requires`
  and `After` the daemon unit.

`packaging/install.sh` copies both into `~/.config/systemd/user/`, runs
`systemctl --user daemon-reload`, checks `input` group membership (warning that
the first addition needs a re-login), and stops and disables any running
`dictate*` units so the two never fight over the microphone or the key. It does
not enable the voxkey units at boot; the tray is the on/off switch.

## 9. Testing

TDD on the pure logic; the GTK and tray shells carry none and are not
unit-tested, matching the parent design's rule.

- `write_settings`: changing one key rewrites only that value; other keys,
  their order, and comments survive; an invalid value raises `ConfigError` and
  the file on disk is unchanged; a missing file is created with only the edited
  keys; the write is atomic.
- `units_to_restart`: each key maps to the right unit set; `language` and sound
  map to the empty set; a multi-key change unions correctly.
- the state-to-icon mapping: every state resolves to an asset path and a
  tooltip; an unknown state falls back to `idle`; a down daemon forces `off`.
- `key_name_from_code`: round-trips against `keyboard.resolve_key` for a sample
  of keys, and rejects an unmapped code.
- `status_view`: assembles the expected strings from a `Config` and flags,
  with no device or keyboard present.

No test requires a display, a keyboard, a microphone or systemd. CI stays on
`ubuntu-latest` with no hardware, as the parent design requires.

## 10. Traps

- **Lazy GTK import.** Importing GTK at module top would make `voxkey serve` on
  a headless box fail. Import inside the handler; translate the ImportError.
- **Decimal separator.** The end-sound "Tester" button plays through
  `output/sound.py`, which already forces `LC_NUMERIC=C` for `pw-play`. The
  Settings form must likewise format the `*_secs` values it writes with a `.`
  separator regardless of locale, or a `fr_FR` locale writes `1,0` and
  `config.parse` rejects it.
- **No device grab on capture.** Key capture must read without `grab()`, or it
  would steal the key from the running PTT client mid-session.
- **State file races.** All writes go through the atomic temp-then-rename helper
  already in `state.py`; the tray reader never sees a half-written line.

## 11. Deferred, restated

Vocabulary tab, Journal tab, microphone selection, dictate migration, and the
headless server unit are a second lot. This one is the tray, the Status and
Settings tabs, and the systemd units that make the tray's on/off switch work.
