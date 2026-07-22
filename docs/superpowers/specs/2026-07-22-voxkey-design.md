# voxkey design

Date: 2026-07-22
Status: approved, awaiting implementation plan

## 1. What this is

voxkey is push-to-talk dictation for Linux. Hold a key, speak, release, and the
transcribed text lands in the clipboard ready to paste. Transcription runs
locally through faster-whisper, on GPU when CUDA is available and on CPU
otherwise. Nothing leaves the machine unless the user explicitly delegates
transcription to a GPU server on their own network.

The project is a full rewrite of `dictate`, a single 1305 line Python script
that grew out of a fork of `vimalk78/dictate`. The rewrite exists to make the
project publishable: modular code, a real test suite, packaging, tooling, an
English-first interface, and a graphical front end.

### Goals

- Preserve every behaviour of the current tool, including the hard-won
  workarounds listed in section 14.
- Make the code testable without a microphone, a keyboard, a GPU or an X server.
- Ship an interface that someone who will never open a TOML file can use.
- Be installable with a single `pipx install voxkey`.

### Non-goals

- Real-time streaming transcription. The tool records, then transcribes.
- Windows or macOS support. evdev, PipeWire and xsel are Linux specific.
- Speaker diarisation, punctuation models, or any post-processing beyond what
  Whisper already returns.

## 2. Naming and provenance

The project is renamed from `dictate` to `voxkey`. `dictate` is the upstream
name and a generic English verb; `voxkey` describes the product exactly, is
free on both PyPI and GitHub, and separates the rewrite from its origin.

The upstream project is MIT licensed. Publication reactivates the attribution
requirement for whatever remains derived, and a rewrite does not erase that,
since the architecture and the protocols are deliberately preserved. The
project therefore ships a `LICENSE` file carrying two copyright lines, the
upstream author's for the derived part and `Evaexe117`'s for the rest, and the
README opens by stating that voxkey began as a fork of `vimalk78/dictate` and
has since been rewritten.

## 3. Package layout

```
voxkey/
├── pyproject.toml
├── LICENSE
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CLAUDE.md
├── .github/workflows/ci.yml
├── src/voxkey/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── paths.py
│   ├── config.py
│   ├── i18n.py
│   ├── state.py
│   ├── hints.py
│   ├── locales/
│   │   ├── voxkey.pot
│   │   ├── en/LC_MESSAGES/voxkey.po
│   │   └── fr/LC_MESSAGES/voxkey.po
│   ├── audio/
│   │   ├── devices.py
│   │   ├── calibration.py
│   │   └── capture.py
│   ├── transcribe/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── remote.py
│   ├── ipc/
│   │   ├── protocol.py
│   │   ├── server.py
│   │   └── client.py
│   ├── net/
│   │   └── tcp.py
│   ├── ptt/
│   │   ├── keyboard.py
│   │   └── client.py
│   ├── output/
│   │   ├── clipboard.py
│   │   └── sound.py
│   ├── tray/
│   │   ├── app.py
│   │   └── assets/
│   └── gui/
│       ├── app.py
│       ├── page_status.py
│       ├── page_settings.py
│       ├── page_vocabulary.py
│       └── page_journal.py
├── packaging/
│   ├── systemd/
│   │   ├── voxkey.service
│   │   ├── voxkey-ptt.service
│   │   └── voxkey-server.service
│   ├── voxkey.desktop
│   ├── voxkey-tray.desktop
│   ├── voxkey-editor
│   ├── voxkey-resume
│   ├── build-ctranslate2.sh
│   ├── claude-code/
│   │   ├── voxkey.md
│   │   └── voxkey-hints.md
│   └── install.sh
└── tests/
```

The rule that governs the whole split: **code that touches hardware is reduced
to thin shells behind a protocol, and all logic is pure and testable**.
`capture.py` receives an audio source, it does not open a microphone.
`ptt/client.py` is a state machine consuming events, it does not read
`/dev/input`.

## 4. CLI surface

Subcommands, not flags. Each mode owns its help text and its options, which the
current flat flag list cannot express: today `--listen` and `--server` are only
meaningful alongside `--serve`, and nothing says so.

```
voxkey serve                          local daemon, keeps the model resident
voxkey serve --listen HOST:PORT       headless transcription server, no mic
voxkey serve --remote HOST:PORT       record locally, transcribe elsewhere
voxkey listen                         push-to-talk client, drives the daemon
voxkey once                           one dictation, text on stdout
voxkey lang [CODE]                    cycle or set the transcription language
voxkey stop                           stop the daemon
voxkey devices                        list audio devices and keyboards
voxkey gui                            open the control window
voxkey tray                           run the tray icon
```

`--server` becomes `--remote`, because `serve --server` was self contradictory.

`cli.py` only parses and dispatches. It contains no behaviour, so the argument
surface can be tested by asserting on the parsed namespace alone.

## 5. Components

Each entry states what the unit does, how it is used, and what it depends on.

**`paths.py`** resolves every filesystem location from the XDG environment and
is the single source of truth for paths. Nothing else calls `expanduser`.
Depends on nothing.

**`config.py`** loads the TOML file into a validated `Config` dataclass.
Unknown keys and wrong types raise at startup with the key name and what was
expected, instead of being ignored or exploding later inside the audio thread.
Depends on `paths`.

**`state.py`** reads and writes the small runtime files: current language,
current state, sound muted. All writes are atomic, write to a temporary file
then rename, because the tray reads these files concurrently. Depends on
`paths`.

**`hints.py`** merges the global vocabulary directory with the per-project one
and returns the string handed to Whisper as `initial_prompt`. Merging happens
per request, so switching projects needs no restart. Pure function over
directory contents. Depends on `paths`.

**`audio/devices.py`** enumerates input devices and picks a default, preferring
the PipeWire device by name over the ALSA `default` device. Thin shell over
`sounddevice`.

**`audio/calibration.py`** derives the speech threshold from a sample of
ambient noise: `ambient * 1.5 + 0.01`, capped at `0.05`. Retries on silence and
on a suspiciously loud reading, which is what catches PipeWire route switching.
Pure function over an array of samples, so every branch is testable with
synthetic signals.

**`audio/capture.py`** maintains the rolling pre-buffer and implements
record-until-silence. Receives an `AudioSource` protocol, never opens a device
itself.

**`transcribe/base.py`** declares the `Transcriber` protocol: given audio, a
language and an initial prompt, return text. Two implementations, `local.py`
over faster-whisper and `remote.py` over TCP, plus `FakeTranscriber` in the
tests.

**`ipc/`** is the Unix socket daemon and its client, split into the wire
protocol, the server loop and the client. The protocol module is pure
serialisation, so round trips are testable without a socket.

**`net/tcp.py`** implements the remote framing: a uint32 header length, a JSON
header, then raw float32 audio at 16 kHz mono. Encoding and decoding are pure
and tested together.

**`ptt/keyboard.py`** discovers keyboards through evdev and yields key events.
Thin shell. **`ptt/client.py`** is the press and release state machine that
applies the minimum hold duration and drives the daemon. It consumes events
from an iterator, so the tests replay a scripted sequence.

**`output/clipboard.py`** writes to the X selection through `xsel`.
**`output/sound.py`** plays notification sounds through `pw-play`, forcing
`LC_NUMERIC=C` on the child environment.

**`tray/app.py`** is the status icon. It reads state files and launches
commands. No business logic.

**`gui/`** is the control window, described in section 8.

## 6. Protocols

Unchanged from the current implementation, so a new client and an old daemon
interoperate during migration.

```
Client to daemon    {"language": "en", "initial_prompt": "..."}
                    then shutdown(SHUT_WR)
Daemon to client    {"status": "recording"}\n
                    {"status": "transcribing"}\n
                    {"text": "..."}\n

Daemon to server    uint32 header length, JSON header, raw float32 audio
Server to daemon    {"text": "..."}\n
```

## 7. Configuration

`$XDG_CONFIG_HOME/voxkey/config.toml`, loaded into a validated dataclass.

| Key | Meaning | Default |
|---|---|---|
| `language` | transcription language | `"en"` |
| `languages` | languages cycled by `voxkey lang` | `["en", "fr"]` |
| `model` | Whisper model | auto, see below |
| `key` | push-to-talk key, without the `KEY_` prefix | `"RIGHTCTRL"` |
| `pre_buffer_secs` | audio kept before recording starts | `1.0` |
| `silence_secs` | silence after speech before stopping | `3.0` |
| `wait_secs` | time to wait for speech before giving up | `10.0` |
| `log_transcripts` | write transcribed text to the logs | `false` |
| `remote` | remote transcription server, `HOST:PORT` | unset |

The English and French defaults replace the `["en", "hi"]` pair inherited from
upstream.

The model default is derived from the machine rather than hardcoded: `medium`
with `int8` on CUDA, `small` with `int8` on CPU. Setting `model` overrides the
choice, and a command line option overrides the file.

This fixes an inconsistency in the current project: the README documents
`model` as a configuration key, but the code only ever reads it from a command
line flag, so setting it in the TOML file does nothing. In voxkey every
setting is readable from the file, and the command line overrides the file
for all of them.

Language names shown in notifications are derived from the language code
through the standard library rather than read from a hardcoded table, which
today lists eight languages and silently falls back to the raw code for every
other one.

`log_transcripts` stays off by default. The daemon and the push-to-talk client
both run under systemd, so anything they print reaches journald. With the
setting off, the logs keep timings, metrics and errors, and record the length
of the text rather than the text.

## 8. Control window

A GTK3 window, opened by `voxkey gui`, by the tray menu, or by the desktop
entry. It contains **no business logic**: it drives the daemon through the same
Unix socket every other client uses, and it edits the same TOML file. Two
sources of truth would inevitably diverge.

PyGObject is an **optional dependency**, installed by `pip install voxkey[gui]`.
A headless GPU box running `voxkey serve --listen` must not need GTK.

Four tabs.

**Status.** Daemon up or down, model name, compute device, selected microphone,
current language, and the configured push-to-talk key. Three actions: start or
stop the daemon, dictate once, cycle the language.

**Settings.** Push-to-talk key, language list, model, microphone, the three
timing thresholds, end-of-dictation sound, and the transcript logging switch.
The TOML file remains the source of truth; the window writes it back, comments
preserved, and reloads the daemon.

**Vocabulary.** Edits the global hints directory and shows the current
project's hints read only, since those belong to the project directory.

**Journal.** Recent events with their durations, which is what makes phantom
presses and hallucinations visible. Transcribed text appears only when
`log_transcripts` is on, so the window never becomes a way to leak what the
setting was meant to keep out of the logs.

The tray icon stays. It is the permanent status indicator and the quiet path,
which is the daily gesture; the window is the configuration surface.

## 9. Internationalisation

gettext, with English source strings and a French catalogue. The locale comes
from the environment. `.mo` files are compiled at build time, so no runtime
dependency on `msgfmt`.

**Only human-facing strings are translated. Log messages stay English.** A
translated log is a log that can no longer be searched, and it ends up pasted
into a bug report read by someone who does not speak the language.

## 10. Testing

The current project has no tests at all. This section is what decides whether
the rewrite is worth doing.

**Test doubles at the three hardware boundaries.** `FakeTranscriber` returns
scripted text. `SyntheticAudioSource` produces known signals: silence, speech,
noise, and a sudden loud reading. `ReplayKeyEvents` replays a list of presses
with their durations.

**Pure functions tested directly.** Speech threshold derivation, minimum hold
filtering, hints merging, config validation and its error messages, TCP frame
encoding and decoding, IPC message round trips, language cycling.

**One real integration test.** The full daemon on a real Unix socket in a
temporary directory, with a fake audio source and a fake transcriber. This
exercises the actual socket code rather than an imitation of it.

**No test requires a microphone, a GPU, a keyboard or an X server.** CI runs on
`ubuntu-latest` with no hardware.

**Known traps become named regression tests.** A 0.4 second press must be
rejected. `play_sound` must pass `LC_NUMERIC=C` to the child. `find_audio_device`
must prefer the PipeWire device over `default`. Calibration must retry on a
suspiciously loud reading.

## 11. Packaging and distribution

`pyproject.toml` with hatchling. One console entry point, `voxkey`, since every
mode is a subcommand. `voxkey-tray` and `voxkey-gui` exist only as desktop
entries invoking `voxkey tray` and `voxkey gui`, so there is a single command
to document and a single argument parser to test. Optional extra `gui` pulling
PyGObject.

`packaging/voxkey-editor` stays a shell script wrapping nvim with voice
keybindings, used as `EDITOR=voxkey-editor claude`. It is not Python, so it is
installed by `install.sh` rather than declared as an entry point.

Published to PyPI as `voxkey`. Recommended installation is `pipx install
voxkey`. `packaging/install.sh` shrinks to what pipx cannot do: install the
systemd user units, install the desktop entries, and check membership of the
`input` group, which reading `/dev/input/event*` requires and which needs a
session restart the first time.

The Jetson Orin Nano path is preserved. JetPack ships Python 3.10 with no
ctranslate2 CUDA wheel for aarch64, so `packaging/build-ctranslate2.sh` builds
one first and `install.sh` detects the architecture, installs that wheel, skips
`nvidia-cublas-cu12` since CUDA comes from JetPack, and points the launcher at
`/usr/local/cuda/lib64`.

CI on GitHub Actions: `ruff`, `mypy --strict`, `pytest`, on Python 3.11, 3.12
and 3.13.

## 12. Claude Code integration

Two slash commands ship under `packaging/claude-code/` and are installed by
`install.sh` into the user's Claude Code commands directory.

`voxkey` chains dictations in a loop and accumulates the utterances, so a long
spoken instruction can be dictated in several breaths. `voxkey-hints` scans the
current codebase and generates the vocabulary hints file for it, which is what
makes class names, library names and acronyms transcribe correctly.

Both are plain Markdown prompt files. They are the reason `voxkey once` must
keep printing bare text on stdout and nothing else.

## 13. Migration from dictate

On first run, if `~/.config/dictate/` exists and `~/.config/voxkey/` does not,
voxkey copies the configuration, the hints directory and the runtime state,
then reports what it did. Nothing is deleted; the old directory stays until the
user removes it.

`install.sh` stops and disables the old `dictate*` units before installing the
new ones, so the two do not compete for the microphone or the socket.

Two scripts disappear. `update.sh` existed because the repository was the
source of truth and the installed copy derived from it by hand; a real package
removes that whole class of problem, and with it the failure mode where editing
the installed copy got the change silently destroyed on the next update.
`debug.sh` is replaced by `voxkey devices`, the Journal tab, and the systemd
journal, which is where the useful evidence already lives.

## 14. Traps that must survive the rewrite

These are the most valuable thing the current repository contains. Each one
cost a debugging session and each one becomes a test.

**Decimal separator.** The machine runs `LC_NUMERIC=fr_FR.UTF-8`. `pw-play`
parses `--volume` with `strtof`, which honours the locale, so `"0.5"` stops at
the dot and becomes zero, which is silence. Any float handed to a C binary as
an argument needs `LC_NUMERIC=C` on the child environment.

**The push-to-talk key is also a modifier.** With the `RIGHTCTRL` default,
every Ctrl+V paste retriggers a recording. Those phantom presses last a few
tenths of a second and Whisper fills the silence with subtitle boilerplate,
which then overwrites the clipboard the paste just consumed. A minimum hold of
one second discards them. Measured: every press under 0.6 s was a phantom, and
the shortest genuine dictation was 2.0 s. A phrase blacklist is not enough,
since observed hallucinations include unlisted text.

**The push-to-talk unit needs the `sg input` wrapper.** The desktop session
does not carry the `input` group, so `ExecStart` goes through
`/usr/bin/sg input -c "..."`. Without it the client exits immediately with
"No keyboard found". Side effect: the process becomes setgid, so
`/proc/<pid>/environ` is unreadable and its environment cannot be inspected
from outside.

**Clipboard uses `xsel`, not `wl-copy`.** `wtype` does not work under GNOME
Wayland, and `xsel` is focus independent.

**PipeWire device selection.** The `default` ALSA device does not route a
Bluetooth microphone correctly, so device selection prefers the PipeWire device
by name.

**`hotwords` degrades transcription** when many terms are supplied. Use
`initial_prompt` instead.

**`hallucination_silence_threshold=2`** keeps Whisper from inventing text over
silence.

## 15. Repository and publication

A new repository, `Evaexe117/voxkey`, public, with a fresh history. The
existing `Evaexe117/dictate` stays private and archived: the rewrite is a clean
break and merging the two histories buys nothing.

Commits are authored `Evaexe117`. The repository must contain no reference to
any other identity.

## 16. Out of scope for this spec

- The exact visual design of the control window beyond its four tabs.
- Any distribution packaging beyond PyPI, such as AUR, Flatpak or .deb.
- Model management, such as downloading or pruning Whisper weights.
