# voxkey Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the voxkey Python package so that `voxkey serve`, `voxkey listen`, `voxkey once`, `voxkey lang`, `voxkey stop` and `voxkey devices` fully replace the current `dictate` script, with a test suite that needs no microphone, keyboard, GPU or X server.

**Architecture:** Code that touches hardware is reduced to thin shells behind a Protocol; all decision logic lives in pure functions and state machines that tests drive directly. A daemon holds the Whisper model resident behind a Unix socket; clients are cheap and restartable. Transcription is an interchangeable implementation, local or remote or fake.

**Tech Stack:** Python 3.12+, faster-whisper, sounddevice, numpy, evdev, stdlib `tomllib`, `gettext`, `argparse`, `socket`. pytest, ruff, mypy. Hatchling for packaging.

This is plan 1 of 3. Plan 2 covers the tray and the GTK control window. Plan 3 covers packaging, migration, documentation and publication. This plan produces working, installable software on its own.

Source of truth: `docs/superpowers/specs/2026-07-22-voxkey-design.md`.

## Global Constraints

- **Python 3.12 minimum.** `tomllib` is stdlib from 3.11, so the `tomli` dependency of the current project disappears. The floor is 3.12 rather than 3.11 because the type stubs numpy ships use PEP 695 `type` statements, which mypy cannot parse under `python_version = "3.11"`. CI runs 3.12 and 3.13.
- **Every module passes `ruff check` and `mypy --strict`.** No `Any` escapes without a comment naming the third-party stub gap that forces it.
- **English only** in code, docstrings, comments, log messages and test names. Human-facing strings are wrapped in `_()` from `voxkey.i18n`; log messages are not.
- **No test may require** a microphone, a keyboard, a GPU, an X server, a network peer, or a real Whisper model. Tests that would need one use the doubles built in Tasks 8, 12 and 15.
- **No test may write outside `tmp_path`.** Every test that touches the filesystem sets `XDG_CONFIG_HOME` and `XDG_DATA_HOME` through the `xdg` fixture from Task 1.
- **`from __future__ import annotations`** at the top of every module.
- **Runtime dependencies:** `faster-whisper`, `sounddevice`, `numpy`, `evdev`. Nothing else. PyGObject arrives in plan 2 as the optional `gui` extra.
- **Commits** are authored `Evaexe117 <58178043+Evaexe117@users.noreply.github.com>`, which is already set in the repository's local config. No `Co-Authored-By` trailer.

---

### Task 1: Project skeleton, tooling, and `paths.py`

Everything else imports `paths`, so it comes first and it brings the build and test scaffolding with it.

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/voxkey/__init__.py`
- Create: `src/voxkey/paths.py`
- Create: `tests/conftest.py`
- Create: `tests/test_paths.py`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: `voxkey.paths` with `config_dir()`, `data_dir()`, `config_file()`, `hints_dir()`, `socket_file()`, `pid_file()`, `language_file()`, `state_file()`, `sound_file()`, `stop_file()`, `legacy_config_dir()`, `legacy_data_dir()`, all returning `pathlib.Path`, plus the constant `PROJECT_HINTS_DIRNAME: str`. Also produces the pytest fixture `xdg` used by every later task.

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest


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
```

`tests/test_paths.py`:

```python
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


def test_every_file_lives_under_its_directory(xdg: Path) -> None:
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL, collection error, `ModuleNotFoundError: No module named 'voxkey'`.

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "voxkey"
version = "0.1.0"
description = "Push-to-talk dictation for Linux, transcribed locally"
readme = "README.md"
requires-python = ">=3.12"
license = { file = "LICENSE" }
authors = [{ name = "Evaexe117" }]
keywords = ["dictation", "speech-to-text", "whisper", "push-to-talk", "linux"]
classifiers = [
    "Environment :: Console",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Multimedia :: Sound/Audio :: Speech",
]
dependencies = [
    "faster-whisper",
    "sounddevice",
    "numpy",
    "evdev",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "ruff", "mypy"]

[project.scripts]
voxkey = "voxkey.cli:main"

[project.urls]
Homepage = "https://github.com/Evaexe117/voxkey"
Issues = "https://github.com/Evaexe117/voxkey/issues"

[tool.hatch.build.targets.wheel]
packages = ["src/voxkey"]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "PTH", "RET", "SIM", "ARG"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests", "tools"]

[[tool.mypy.overrides]]
module = ["sounddevice", "evdev", "faster_whisper"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

`.gitignore`:

```
__pycache__/
*.py[cod]
.venv/
dist/
build/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
src/voxkey/locales/**/*.mo
```

- [ ] **Step 4: Write `src/voxkey/__init__.py` and `src/voxkey/paths.py`**

`src/voxkey/__init__.py`:

```python
"""voxkey: push-to-talk dictation for Linux, transcribed locally."""

from __future__ import annotations

__version__ = "0.1.0"
```

`src/voxkey/paths.py`:

```python
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
    return Path(os.path.expanduser("~")) / fallback


def config_dir() -> Path:
    return _xdg_base("XDG_CONFIG_HOME", ".config") / APP_NAME


def data_dir() -> Path:
    return _xdg_base("XDG_DATA_HOME", ".local/share") / APP_NAME


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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pip install -e ".[dev]" && python -m pytest tests/test_paths.py -v`
Expected: 5 passed.

- [ ] **Step 6: Write the CI workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install system libraries
        run: sudo apt-get update && sudo apt-get install -y libportaudio2
      - name: Install
        run: pip install -e ".[dev]"
      - name: Lint
        run: ruff check .
      - name: Type check
        run: mypy
      - name: Test
        run: pytest -v
```

- [ ] **Step 7: Verify lint and types pass locally**

Run: `ruff check . && mypy`
Expected: `All checks passed!` from ruff, `Success: no issues found` from mypy.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .github src tests
git commit -m "Add package skeleton, tooling, and path resolution

Every filesystem location resolves through voxkey.paths, so the xdg fixture
can redirect the whole application into a temporary directory and no test can
reach the developer's real configuration."
```

---

### Task 2: `config.py`

**Files:**
- Create: `src/voxkey/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `voxkey.paths.config_file`.
- Produces: `Config` frozen dataclass with fields `language: str`, `languages: tuple[str, ...]`, `model: str | None`, `key: str`, `pre_buffer_secs: float`, `silence_secs: float`, `wait_secs: float`, `log_transcripts: bool`, `remote: str | None`. Functions `parse(raw: dict[str, object]) -> Config` and `load(path: Path | None = None) -> Config`. Exception `ConfigError(ValueError)`.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from voxkey.config import Config, ConfigError, load, parse


def test_defaults_are_english_first() -> None:
    config = parse({})
    assert config.language == "en"
    assert config.languages == ("en", "fr")
    assert config.key == "RIGHTCTRL"
    assert config.pre_buffer_secs == 1.0
    assert config.silence_secs == 3.0
    assert config.wait_secs == 10.0
    assert config.log_transcripts is False
    assert config.model is None
    assert config.remote is None


def test_values_override_defaults() -> None:
    config = parse({"language": "fr", "key": "PAUSE", "silence_secs": 2})
    assert config.language == "fr"
    assert config.key == "PAUSE"
    assert config.silence_secs == 2.0


def test_integer_is_accepted_where_a_float_is_expected() -> None:
    assert parse({"wait_secs": 5}).wait_secs == 5.0


def test_bool_is_rejected_where_a_float_is_expected() -> None:
    with pytest.raises(ConfigError, match="wait_secs"):
        parse({"wait_secs": True})


def test_unknown_key_names_itself_and_the_known_keys() -> None:
    with pytest.raises(ConfigError) as excinfo:
        parse({"langauge": "fr"})
    message = str(excinfo.value)
    assert "langauge" in message
    assert "language" in message


def test_wrong_type_names_key_expected_and_actual() -> None:
    with pytest.raises(ConfigError) as excinfo:
        parse({"silence_secs": "three"})
    message = str(excinfo.value)
    assert "silence_secs" in message
    assert "number" in message
    assert "str" in message


def test_empty_language_list_is_rejected() -> None:
    with pytest.raises(ConfigError, match="languages"):
        parse({"languages": []})


def test_non_positive_durations_are_rejected() -> None:
    for key in ("pre_buffer_secs", "silence_secs", "wait_secs"):
        with pytest.raises(ConfigError, match=key):
            parse({key: 0})


def test_remote_must_look_like_host_port() -> None:
    assert parse({"remote": "10.0.0.2:5555"}).remote == "10.0.0.2:5555"
    with pytest.raises(ConfigError, match="remote"):
        parse({"remote": "10.0.0.2"})


def test_load_returns_defaults_when_the_file_is_absent(xdg: Path) -> None:
    assert load() == Config()


def test_load_reads_the_config_file(xdg: Path) -> None:
    from voxkey import paths

    paths.config_file().write_text(
        textwrap.dedent(
            """
            language = "fr"
            languages = ["fr", "en"]
            key = "PAUSE"
            """
        )
    )
    config = load()
    assert config.language == "fr"
    assert config.languages == ("fr", "en")
    assert config.key == "PAUSE"


def test_load_reports_the_path_on_malformed_toml(xdg: Path) -> None:
    from voxkey import paths

    paths.config_file().write_text("language = ")
    with pytest.raises(ConfigError) as excinfo:
        load()
    assert str(paths.config_file()) in str(excinfo.value)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.config'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/config.py`:

```python
"""Load and validate the user's configuration.

The current dictate script ignores unknown keys silently and lets a wrong type
crash deep inside the audio thread. Here every problem is reported at startup,
naming the key, what was expected and what was found.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from voxkey import paths


class ConfigError(ValueError):
    """The configuration file is unusable. The message names the key."""


@dataclass(frozen=True, slots=True)
class Config:
    language: str = "en"
    languages: tuple[str, ...] = ("en", "fr")
    model: str | None = None
    key: str = "RIGHTCTRL"
    pre_buffer_secs: float = 1.0
    silence_secs: float = 3.0
    wait_secs: float = 10.0
    log_transcripts: bool = False
    remote: str | None = None


_DURATION_KEYS = ("pre_buffer_secs", "silence_secs", "wait_secs")


def _known_keys() -> tuple[str, ...]:
    return tuple(field.name for field in fields(Config))


def _as_str(key: str, value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError(
            f"{key}: expected a string, found {type(value).__name__}"
        )
    return value


def _as_number(key: str, value: object) -> float:
    # bool is a subclass of int, and "silence_secs = true" is always a mistake.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"{key}: expected a number, found {type(value).__name__}"
        )
    return float(value)


def _as_bool(key: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(
            f"{key}: expected true or false, found {type(value).__name__}"
        )
    return value


def _as_language_list(key: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{key}: expected a non-empty list of language codes")
    return tuple(_as_str(key, item) for item in value)


def _as_address(key: str, value: object) -> str:
    text = _as_str(key, value)
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ConfigError(f"{key}: expected HOST:PORT, found {text!r}")
    return text


def parse(raw: dict[str, object]) -> Config:
    """Validate a raw mapping and build a Config. Pure, so it is directly testable."""
    unknown = sorted(set(raw) - set(_known_keys()))
    if unknown:
        known = ", ".join(_known_keys())
        raise ConfigError(
            f"unknown configuration key(s): {', '.join(unknown)}. Known keys: {known}"
        )

    values: dict[str, object] = {}
    if "language" in raw:
        values["language"] = _as_str("language", raw["language"])
    if "languages" in raw:
        values["languages"] = _as_language_list("languages", raw["languages"])
    if "model" in raw:
        values["model"] = _as_str("model", raw["model"])
    if "key" in raw:
        values["key"] = _as_str("key", raw["key"])
    for key in _DURATION_KEYS:
        if key in raw:
            seconds = _as_number(key, raw[key])
            if seconds <= 0:
                raise ConfigError(f"{key}: expected a positive number, found {seconds}")
            values[key] = seconds
    if "log_transcripts" in raw:
        values["log_transcripts"] = _as_bool("log_transcripts", raw["log_transcripts"])
    if "remote" in raw:
        values["remote"] = _as_address("remote", raw["remote"])

    return Config(**values)  # type: ignore[arg-type]  # validated above


def load(path: Path | None = None) -> Config:
    """Read the configuration file, or return defaults when it does not exist."""
    target = path if path is not None else paths.config_file()
    try:
        raw_bytes = target.read_bytes()
    except FileNotFoundError:
        return Config()
    try:
        raw = tomllib.loads(raw_bytes.decode())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ConfigError(f"{target}: {error}") from error
    return parse(raw)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v && ruff check . && mypy`
Expected: 12 passed, ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/config.py tests/test_config.py
git commit -m "Validate configuration at startup instead of failing later

Unknown keys and wrong types now raise with the key name, what was expected
and what was found, rather than being ignored or exploding inside the audio
thread. Defaults become English first with French second."
```

---

### Task 3: `i18n.py` and the catalogue compiler

The catalogue compiler is written in Python rather than shelling out to `msgfmt`, so building and testing never depend on gettext tools being installed.

**Files:**
- Create: `src/voxkey/i18n.py`
- Create: `src/voxkey/locales/voxkey.pot`
- Create: `src/voxkey/locales/fr/LC_MESSAGES/voxkey.po`
- Create: `tools/compile_catalogs.py`
- Create: `tests/test_i18n.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `voxkey.i18n` with `setup(languages: Sequence[str] | None = None) -> None` and `_(message: str) -> str`. `tools.compile_catalogs` with `compile_po(po_text: str) -> bytes` and `main() -> int`.

- [ ] **Step 1: Write the failing test**

`tests/test_i18n.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compile_catalogs import compile_po  # noqa: E402

from voxkey import i18n  # noqa: E402

FRENCH_PO = """
msgid ""
msgstr "Content-Type: text/plain; charset=UTF-8\\n"

msgid "Recording"
msgstr "Enregistrement"

msgid "No speech detected"
msgstr "Aucune parole detectee"
"""


def test_untranslated_message_passes_through() -> None:
    i18n.setup(["en"])
    assert i18n._("Recording") == "Recording"


def test_compiled_catalogue_is_a_valid_mo_file() -> None:
    data = compile_po(FRENCH_PO)
    assert data[:4] in (b"\xde\x12\x04\x95", b"\x95\x04\x12\xde")


def test_french_catalogue_translates(tmp_path: Path) -> None:
    target = tmp_path / "fr" / "LC_MESSAGES"
    target.mkdir(parents=True)
    (target / "voxkey.mo").write_bytes(compile_po(FRENCH_PO))

    i18n.setup(["fr"], localedir=tmp_path)
    assert i18n._("Recording") == "Enregistrement"
    assert i18n._("Unknown string") == "Unknown string"


def test_setup_falls_back_when_the_language_has_no_catalogue(tmp_path: Path) -> None:
    i18n.setup(["de"], localedir=tmp_path)
    assert i18n._("Recording") == "Recording"


def test_accented_translations_survive_compilation() -> None:
    # The catalogue exists to carry accented French. A compiler that mangles
    # it is worse than no compiler, and ASCII-only fixtures hide the damage.
    po = (
        'msgid ""\n'
        'msgstr "Content-Type: text/plain; charset=UTF-8\\n"\n'
        "\n"
        'msgid "No speech detected"\n'
        'msgstr "Aucune parole détectée"\n'
    )
    assert "Aucune parole détectée".encode() in compile_po(po)


def test_escape_sequences_are_resolved() -> None:
    po = 'msgid "a"\nmsgstr "one\\ttwo\\nthree"\n'
    assert b"one\ttwo\nthree" in compile_po(po)


def test_shipped_french_catalogue_compiles_with_its_accents() -> None:
    po = Path("src/voxkey/locales/fr/LC_MESSAGES/voxkey.po").read_text()
    compiled = compile_po(po)
    assert "Aucune parole détectée".encode() in compiled
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_i18n.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tools'`.

- [ ] **Step 3: Write the catalogue compiler**

`tools/compile_catalogs.py`:

```python
"""Compile .po catalogues into .mo files without depending on gettext tools.

The MO format is a small, stable, documented binary layout, so implementing it
here removes a build dependency that would otherwise have to be present on
every machine that builds a wheel.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MAGIC = 0x950412DE

# The escapes gettext defines inside a quoted PO string.
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _unquote(text: str) -> str:
    """Resolve PO escape sequences without touching anything else.

    The obvious shortcut, ``text.encode().decode("unicode_escape")``, silently
    mangles every non-ASCII character: it encodes as UTF-8 and decodes as
    Latin-1, so "détectée" comes back as mojibake. Accented translations are
    the entire point of shipping a French catalogue, so the escapes are
    resolved by hand instead.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            index += 1
            out.append(_ESCAPES.get(text[index], text[index]))
        else:
            out.append(char)
        index += 1
    return "".join(out)


def parse_po(po_text: str) -> dict[str, str]:
    """Extract msgid/msgstr pairs. Fuzzy and empty translations are dropped."""
    entries: dict[str, str] = {}
    msgid: list[str] = []
    msgstr: list[str] = []
    current: str | None = None
    fuzzy = False
    pending_fuzzy = False

    def flush() -> None:
        nonlocal msgid, msgstr, current, fuzzy
        if current is not None:
            key = "".join(msgid)
            value = "".join(msgstr)
            if value and not fuzzy:
                entries[key] = value
        msgid, msgstr, current, fuzzy = [], [], None, False

    for raw_line in po_text.splitlines():
        line = raw_line.strip()
        if line.startswith("#,") and "fuzzy" in line:
            pending_fuzzy = True
            continue
        if line.startswith("#") or not line:
            continue
        if line.startswith("msgid "):
            flush()
            fuzzy = pending_fuzzy
            pending_fuzzy = False
            current = "msgid"
            msgid.append(_unquote(line[len("msgid ") :].strip('"')))
        elif line.startswith("msgstr "):
            current = "msgstr"
            msgstr.append(_unquote(line[len("msgstr ") :].strip('"')))
        elif line.startswith('"') and current == "msgid":
            msgid.append(_unquote(line.strip('"')))
        elif line.startswith('"') and current == "msgstr":
            msgstr.append(_unquote(line.strip('"')))
    flush()
    return entries


def compile_po(po_text: str) -> bytes:
    """Render the catalogue as a little-endian MO file."""
    entries = parse_po(po_text)
    keys = sorted(entries)
    ids = b"\x00".join(key.encode() for key in keys) + (b"\x00" if keys else b"")
    strings = b"\x00".join(entries[key].encode() for key in keys) + (
        b"\x00" if keys else b""
    )

    count = len(keys)
    key_table_offset = 28
    value_table_offset = key_table_offset + count * 8
    ids_offset = value_table_offset + count * 8
    strings_offset = ids_offset + len(ids)

    key_table = b""
    value_table = b""
    id_cursor = ids_offset
    string_cursor = strings_offset
    for key in keys:
        encoded_key = key.encode()
        encoded_value = entries[key].encode()
        key_table += struct.pack("<II", len(encoded_key), id_cursor)
        value_table += struct.pack("<II", len(encoded_value), string_cursor)
        id_cursor += len(encoded_key) + 1
        string_cursor += len(encoded_value) + 1

    header = struct.pack(
        "<IiIIIii", MAGIC, 0, count, key_table_offset, value_table_offset, 0, 0
    )
    return header + key_table + value_table + ids + strings


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "src" / "voxkey" / "locales"
    compiled = 0
    for po_path in root.rglob("*.po"):
        mo_path = po_path.with_suffix(".mo")
        mo_path.write_bytes(compile_po(po_path.read_text()))
        print(f"compiled {po_path} -> {mo_path}")
        compiled += 1
    if compiled == 0:
        print("no catalogues found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write the catalogues**

`src/voxkey/locales/voxkey.pot`:

```
msgid ""
msgstr ""
"Project-Id-Version: voxkey 0.1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid "Recording"
msgstr ""

msgid "Transcribing"
msgstr ""

msgid "No speech detected"
msgstr ""

msgid "Language: {name} ({code})"
msgstr ""
```

`src/voxkey/locales/fr/LC_MESSAGES/voxkey.po`:

```
msgid ""
msgstr ""
"Project-Id-Version: voxkey 0.1.0\n"
"Language: fr\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid "Recording"
msgstr "Enregistrement"

msgid "Transcribing"
msgstr "Transcription"

msgid "No speech detected"
msgstr "Aucune parole détectée"

msgid "Language: {name} ({code})"
msgstr "Langue : {name} ({code})"
```

- [ ] **Step 5: Write `src/voxkey/i18n.py`**

```python
"""Translation of human-facing strings.

Only strings a person reads are translated. Log messages stay English: a
translated log cannot be searched, and it ends up pasted into a bug report read
by someone who does not speak the language.
"""

from __future__ import annotations

import gettext
from collections.abc import Sequence
from pathlib import Path

DOMAIN = "voxkey"

_active: gettext.NullTranslations = gettext.NullTranslations()


def default_localedir() -> Path:
    return Path(__file__).resolve().parent / "locales"


def setup(languages: Sequence[str] | None = None, localedir: Path | None = None) -> None:
    """Select the catalogue. Falls back to the untranslated strings."""
    global _active
    _active = gettext.translation(
        DOMAIN,
        localedir=str(localedir if localedir is not None else default_localedir()),
        languages=list(languages) if languages is not None else None,
        fallback=True,
    )


def _(message: str) -> str:
    """Translate a human-facing string.

    This indirection exists so that ``setup`` can be called after import: a
    module-level name bound to a translator would freeze the first choice.
    """
    return _active.gettext(message)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python tools/compile_catalogs.py && python -m pytest tests/test_i18n.py -v`
Expected: catalogue compiled, 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/voxkey/i18n.py src/voxkey/locales tools tests/test_i18n.py
git commit -m "Translate human-facing strings, English source with French catalogue

Catalogues compile through a small Python implementation of the MO format
rather than msgfmt, so no machine building a wheel needs gettext installed.
Log messages stay English on purpose."
```

---

### Task 4: `state.py`

**Files:**
- Create: `src/voxkey/state.py`
- Create: `src/voxkey/languages.py`
- Create: `tests/test_state.py`
- Create: `tests/test_languages.py`

**Interfaces:**
- Consumes: `voxkey.paths`, `voxkey.config.Config`, `voxkey.i18n._`.
- Produces: `write_atomic(path: Path, text: str) -> None`, `read_text(path: Path, default: str = "") -> str`, `get_language(config: Config) -> str`, `set_language(code: str) -> None`, `get_state() -> str`, `set_state(value: str) -> None`, `sound_enabled() -> bool`, `set_sound_enabled(enabled: bool) -> None`, `next_language(current: str, languages: Sequence[str]) -> str`, and the constants `STATE_IDLE`, `STATE_RECORDING`, `STATE_TRANSCRIBING`, `STATE_DONE`, `STATE_ERROR`, `STATE_OFF`. Also `voxkey.languages.language_name(code: str) -> str` and `voxkey.languages.NAMES: dict[str, str]`.

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:

```python
from __future__ import annotations

from pathlib import Path

from voxkey import paths, state
from voxkey.config import Config


def test_write_atomic_creates_parent_directories(xdg: Path, tmp_path: Path) -> None:
    target = tmp_path / "deep" / "deeper" / "file"
    state.write_atomic(target, "value")
    assert target.read_text() == "value"


def test_write_atomic_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "file"
    state.write_atomic(target, "value")
    assert [p.name for p in tmp_path.iterdir()] == ["file"]


def test_write_atomic_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "file"
    state.write_atomic(target, "first")
    state.write_atomic(target, "second")
    assert target.read_text() == "second"


def test_read_text_returns_the_default_when_absent(tmp_path: Path) -> None:
    assert state.read_text(tmp_path / "nothing", default="fallback") == "fallback"


def test_language_falls_back_to_the_configured_one(xdg: Path) -> None:
    assert state.get_language(Config(language="fr")) == "fr"


def test_language_file_wins_over_the_configuration(xdg: Path) -> None:
    state.set_language("es")
    assert state.get_language(Config(language="fr")) == "es"
    assert paths.language_file().read_text().strip() == "es"


def test_blank_language_file_is_ignored(xdg: Path) -> None:
    state.write_atomic(paths.language_file(), "   ")
    assert state.get_language(Config(language="fr")) == "fr"


def test_next_language_cycles_and_wraps() -> None:
    assert state.next_language("en", ["en", "fr"]) == "fr"
    assert state.next_language("fr", ["en", "fr"]) == "en"


def test_next_language_of_an_unlisted_code_returns_the_first() -> None:
    assert state.next_language("de", ["en", "fr"]) == "en"


def test_next_language_of_a_single_entry_list_is_itself() -> None:
    assert state.next_language("en", ["en"]) == "en"


def test_sound_is_enabled_unless_explicitly_off(xdg: Path) -> None:
    assert state.sound_enabled() is True
    state.set_sound_enabled(False)
    assert state.sound_enabled() is False
    state.set_sound_enabled(True)
    assert state.sound_enabled() is True


def test_state_round_trips(xdg: Path) -> None:
    state.set_state(state.STATE_RECORDING)
    assert state.get_state() == state.STATE_RECORDING
```

`tests/test_languages.py`:

```python
from __future__ import annotations

from voxkey import languages


def test_known_codes_have_a_readable_name() -> None:
    assert languages.language_name("en") == "English"
    assert languages.language_name("fr") == "French"


def test_an_unknown_code_falls_back_to_itself() -> None:
    assert languages.language_name("zz") == "zz"


def test_the_table_covers_the_configured_defaults() -> None:
    from voxkey.config import Config

    for code in Config().languages:
        assert code in languages.NAMES


def test_lookup_is_case_insensitive() -> None:
    assert languages.language_name("FR") == "French"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_state.py tests/test_languages.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.state'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/state.py`:

```python
"""Small runtime files shared between the daemon, the clients and the tray.

The tray polls these files while the daemon writes them, so every write goes
through a temporary file and a rename. A reader then sees either the old
content or the new one, never a truncated line.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from voxkey import paths
from voxkey.config import Config

STATE_OFF = "off"
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_DONE = "done"
STATE_ERROR = "error"

_SOUND_OFF = "off"
_SOUND_ON = "on"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text()
    except OSError:
        return default


def get_language(config: Config) -> str:
    stored = read_text(paths.language_file()).strip()
    return stored or config.language


def set_language(code: str) -> None:
    write_atomic(paths.language_file(), code)


def next_language(current: str, languages: Sequence[str]) -> str:
    """The language after ``current``, wrapping around. Unknown codes restart the cycle."""
    if not languages:
        return current
    try:
        index = list(languages).index(current)
    except ValueError:
        return languages[0]
    return languages[(index + 1) % len(languages)]


def get_state() -> str:
    return read_text(paths.state_file(), default=STATE_IDLE).strip() or STATE_IDLE


def set_state(value: str) -> None:
    write_atomic(paths.state_file(), value)


def sound_enabled() -> bool:
    return read_text(paths.sound_file(), default=_SOUND_ON).strip() != _SOUND_OFF


def set_sound_enabled(enabled: bool) -> None:
    write_atomic(paths.sound_file(), _SOUND_ON if enabled else _SOUND_OFF)
```

`src/voxkey/languages.py`:

```python
"""Readable names for the language codes Whisper accepts.

dictate carried a table of eight names inline in ``set_language`` and showed
the raw code for anything else. The names are marked for translation, so a
French interface says "Anglais" rather than "English".
"""

from __future__ import annotations

from voxkey.i18n import _

NAMES: dict[str, str] = {
    "ar": "Arabic",
    "cs": "Czech",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "sv": "Swedish",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "zh": "Chinese",
}


def language_name(code: str) -> str:
    """The readable name for a code, or the code itself when unknown."""
    name = NAMES.get(code.casefold())
    return _(name) if name is not None else code
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_state.py tests/test_languages.py -v && ruff check . && mypy`
Expected: 16 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/state.py src/voxkey/languages.py tests/test_state.py tests/test_languages.py
git commit -m "Share runtime state through atomically written files

The tray reads these files while the daemon writes them, so every write goes
through a temporary file and a rename and a reader never sees a partial line."
```

---

### Task 5: `hints.py`

**Files:**
- Create: `src/voxkey/hints.py`
- Create: `tests/test_hints.py`

**Interfaces:**
- Consumes: `voxkey.paths`.
- Produces: `read_hints_file(path: Path) -> list[str]`, `read_hints_dir(directory: Path) -> list[str]`, `deduplicate(words: Iterable[str]) -> list[str]`, `build_prompt(words: Sequence[str]) -> str | None`, `load_hints(project_dir: Path | None = None) -> str | None`.

- [ ] **Step 1: Write the failing test**

`tests/test_hints.py`:

```python
from __future__ import annotations

from pathlib import Path

from voxkey import hints, paths


def test_blank_lines_and_comments_are_dropped(tmp_path: Path) -> None:
    source = tmp_path / "terms"
    source.write_text("Whisper\n\n# a comment\nPipeWire\n")
    assert hints.read_hints_file(source) == ["Whisper", "PipeWire"]


def test_an_indented_comment_is_also_dropped(tmp_path: Path) -> None:
    # The dictate implementation tested the raw line, so an indented comment
    # was kept as a vocabulary term. Strip first, then decide.
    source = tmp_path / "terms"
    source.write_text("Whisper\n   # indented comment\n")
    assert hints.read_hints_file(source) == ["Whisper"]


def test_directory_merges_files_in_sorted_order(tmp_path: Path) -> None:
    (tmp_path / "b.hints").write_text("Beta\n")
    (tmp_path / "a.hints").write_text("Alpha\n")
    assert hints.read_hints_dir(tmp_path) == ["Alpha", "Beta"]


def test_missing_directory_yields_nothing(tmp_path: Path) -> None:
    assert hints.read_hints_dir(tmp_path / "absent") == []


def test_subdirectories_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.hints").write_text("Alpha\n")
    assert hints.read_hints_dir(tmp_path) == ["Alpha"]


def test_deduplication_is_case_insensitive_and_keeps_the_first_spelling() -> None:
    assert hints.deduplicate(["PipeWire", "pipewire", "Whisper"]) == [
        "PipeWire",
        "Whisper",
    ]


def test_prompt_shape_matches_the_dictate_format() -> None:
    assert hints.build_prompt(["Whisper", "PipeWire"]) == (
        "Technical terms: Whisper, PipeWire."
    )


def test_prompt_of_nothing_is_none() -> None:
    assert hints.build_prompt([]) is None


def test_global_and_project_hints_merge(xdg: Path, tmp_path: Path) -> None:
    paths.hints_dir().mkdir(parents=True)
    (paths.hints_dir() / "global.hints").write_text("Whisper\n")

    project = tmp_path / "project"
    (project / paths.PROJECT_HINTS_DIRNAME).mkdir(parents=True)
    (project / paths.PROJECT_HINTS_DIRNAME / "local.hints").write_text("Numpy\n")

    assert hints.load_hints(project) == "Technical terms: Whisper, Numpy."


def test_legacy_project_directory_is_still_read(xdg: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / paths.LEGACY_PROJECT_HINTS_DIRNAME).mkdir(parents=True)
    (project / paths.LEGACY_PROJECT_HINTS_DIRNAME / "l.hints").write_text("Legacy\n")
    assert hints.load_hints(project) == "Technical terms: Legacy."


def test_no_hints_anywhere_yields_none(xdg: Path, tmp_path: Path) -> None:
    assert hints.load_hints(tmp_path / "empty") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_hints.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.hints'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/hints.py`:

```python
"""Vocabulary hints handed to Whisper as its initial prompt.

Proper nouns, acronyms and technical terms transcribe badly without context.
Hints are merged per request, global first then project, so switching project
directories needs no restart.

``hotwords`` degrades transcription when many terms are supplied, which is why
this becomes ``initial_prompt`` instead.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from voxkey import paths


def read_hints_file(path: Path) -> list[str]:
    words: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        words.append(line)
    return words


def read_hints_dir(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    words: list[str] = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if entry.is_file():
            words.extend(read_hints_file(entry))
    return words


def deduplicate(words: Iterable[str]) -> list[str]:
    """Drop repeats case-insensitively, keeping the first spelling seen."""
    seen: set[str] = set()
    unique: list[str] = []
    for word in words:
        folded = word.casefold()
        if folded not in seen:
            seen.add(folded)
            unique.append(word)
    return unique


def build_prompt(words: Sequence[str]) -> str | None:
    if not words:
        return None
    return "Technical terms: " + ", ".join(words) + "."


def load_hints(project_dir: Path | None = None) -> str | None:
    """Merge the global hints directory with the current project's."""
    root = project_dir if project_dir is not None else Path.cwd()
    words = read_hints_dir(paths.hints_dir())
    words.extend(read_hints_dir(root / paths.PROJECT_HINTS_DIRNAME))
    words.extend(read_hints_dir(root / paths.LEGACY_PROJECT_HINTS_DIRNAME))
    return build_prompt(deduplicate(words))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_hints.py -v && ruff check . && mypy`
Expected: 11 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/hints.py tests/test_hints.py
git commit -m "Merge global and project vocabulary hints per request

Fixes a dictate behaviour where an indented comment line was kept as a
vocabulary term, because the raw line was tested for the leading hash before
being stripped."
```

---

### Task 6: `net/tcp.py`

**Files:**
- Create: `src/voxkey/net/__init__.py`
- Create: `src/voxkey/net/tcp.py`
- Create: `tests/test_tcp.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RemoteRequest` dataclass with `language: str`, `initial_prompt: str`, `audio: numpy.ndarray`. Functions `encode_request(request: RemoteRequest) -> bytes`, `decode_request(stream: IO[bytes]) -> RemoteRequest`, `encode_response(text: str) -> bytes`, `encode_error(message: str) -> bytes`, `decode_response(payload: bytes) -> str`. Exception `RemoteError(RuntimeError)`.

> **Implemented beyond this text.** The code below lets `json.JSONDecodeError`,
> `KeyError`, `ValueError`, `TypeError` and `UnicodeDecodeError` escape from
> `decode_request` and `decode_response`, which contradicts `RemoteError`'s own
> docstring and would kill a server loop written to catch `RemoteError` and keep
> serving. Review caught it. The shipped module wraps every malformed-frame path
> in `RemoteError`, chaining the original cause, and rejects a negative or
> wrong-typed `audio_length` and a non-UTF-8 header. Eleven malformed-frame
> cases are covered by tests. See commits `cb62d29` and `b5c55fc`. The byte
> layout below is unchanged and remains authoritative.

- [ ] **Step 1: Write the failing test**

`tests/test_tcp.py`:

```python
from __future__ import annotations

import io
import struct

import numpy as np
import pytest

from voxkey.net.tcp import (
    RemoteError,
    RemoteRequest,
    decode_request,
    decode_response,
    encode_error,
    encode_request,
    encode_response,
)


def test_request_round_trips() -> None:
    audio = np.array([0.0, 0.5, -0.5], dtype=np.float32)
    original = RemoteRequest(language="fr", initial_prompt="Terms: a.", audio=audio)
    decoded = decode_request(io.BytesIO(encode_request(original)))
    assert decoded.language == "fr"
    assert decoded.initial_prompt == "Terms: a."
    np.testing.assert_array_equal(decoded.audio, audio)


def test_frame_starts_with_a_big_endian_header_length() -> None:
    request = RemoteRequest("en", "", np.zeros(1, dtype=np.float32))
    frame = encode_request(request)
    (header_length,) = struct.unpack(">I", frame[:4])
    assert header_length == len(frame) - 4 - 4  # one float32 of audio


def test_audio_is_coerced_to_float32() -> None:
    request = RemoteRequest("en", "", np.array([1.0, 2.0], dtype=np.float64))
    decoded = decode_request(io.BytesIO(encode_request(request)))
    assert decoded.audio.dtype == np.float32


def test_truncated_audio_is_reported() -> None:
    frame = encode_request(RemoteRequest("en", "", np.zeros(4, dtype=np.float32)))
    with pytest.raises(RemoteError, match="truncated"):
        decode_request(io.BytesIO(frame[:-4]))


def test_truncated_header_is_reported() -> None:
    with pytest.raises(RemoteError, match="truncated"):
        decode_request(io.BytesIO(b"\x00\x00"))


def test_response_round_trips() -> None:
    assert decode_response(encode_response("hello")) == "hello"


def test_response_is_newline_terminated() -> None:
    assert encode_response("hello").endswith(b"\n")


def test_error_response_raises() -> None:
    with pytest.raises(RemoteError, match="model exploded"):
        decode_response(encode_error("model exploded"))


def test_empty_response_is_reported() -> None:
    with pytest.raises(RemoteError, match="empty"):
        decode_response(b"")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_tcp.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.net'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/net/__init__.py`:

```python
"""Wire formats for delegating transcription to another machine."""

from __future__ import annotations
```

`src/voxkey/net/tcp.py`:

```python
"""Framing for the remote transcription protocol.

    daemon to server    uint32 big-endian header length, JSON header, raw audio
    server to daemon    one JSON object, newline terminated

Audio is float32, mono, 16 kHz. The format is unchanged from dictate so that a
voxkey daemon and a dictate server interoperate during a staged upgrade.

Encoding and decoding are pure functions over byte streams, so the whole
protocol is tested without opening a socket.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import IO

import numpy as np
import numpy.typing as npt

HEADER_LENGTH_FORMAT = ">I"
HEADER_LENGTH_SIZE = 4
BYTES_PER_SAMPLE = 4


class RemoteError(RuntimeError):
    """The peer reported a failure, or the frame was unusable."""


@dataclass(frozen=True)
class RemoteRequest:
    language: str
    initial_prompt: str
    audio: npt.NDArray[np.float32]


def encode_request(request: RemoteRequest) -> bytes:
    audio = np.asarray(request.audio, dtype=np.float32)
    payload = audio.tobytes()
    header = json.dumps(
        {
            "language": request.language,
            "initial_prompt": request.initial_prompt,
            "audio_length": len(payload),
        }
    ).encode()
    return struct.pack(HEADER_LENGTH_FORMAT, len(header)) + header + payload


def _read_exactly(stream: IO[bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise RemoteError(f"truncated frame: wanted {size} bytes, got {size - remaining}")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def decode_request(stream: IO[bytes]) -> RemoteRequest:
    raw_length = _read_exactly(stream, HEADER_LENGTH_SIZE)
    (header_length,) = struct.unpack(HEADER_LENGTH_FORMAT, raw_length)
    header = json.loads(_read_exactly(stream, header_length).decode())
    payload = _read_exactly(stream, int(header["audio_length"]))
    audio: npt.NDArray[np.float32] = np.frombuffer(payload, dtype=np.float32)
    return RemoteRequest(
        language=str(header.get("language", "en")),
        initial_prompt=str(header.get("initial_prompt", "")),
        audio=audio,
    )


def encode_response(text: str) -> bytes:
    return json.dumps({"text": text}).encode() + b"\n"


def encode_error(message: str) -> bytes:
    return json.dumps({"error": message}).encode() + b"\n"


def decode_response(payload: bytes) -> str:
    text = payload.decode().strip()
    if not text:
        raise RemoteError("empty response from the transcription server")
    message = json.loads(text)
    if "error" in message:
        raise RemoteError(str(message["error"]))
    return str(message.get("text", ""))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_tcp.py -v && ruff check . && mypy`
Expected: 9 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/net tests/test_tcp.py
git commit -m "Frame the remote transcription protocol as pure functions

Encoding and decoding work over byte streams rather than sockets, so the whole
wire format is tested without a network peer. The format is unchanged from
dictate so the two interoperate during an upgrade."
```

---

### Task 7: `ipc/protocol.py`

**Files:**
- Create: `src/voxkey/ipc/__init__.py`
- Create: `src/voxkey/ipc/protocol.py`
- Create: `tests/test_ipc_protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DictationRequest` dataclass with `language: str`, `initial_prompt: str | None`, `wait_secs: float | None`, `silence_secs: float | None`. Messages `StatusMessage(status: str)`, `ResultMessage(text: str)`, `ErrorMessage(message: str)`, union alias `Reply`. Functions `encode_request`, `decode_request`, `encode_reply`, `decode_reply`. Constants `STATUS_RECORDING`, `STATUS_TRANSCRIBING`. Exception `ProtocolError(ValueError)`.

> **Implemented beyond this text.** The code below accepts ill-typed optional
> fields silently: `decode_request` only coerces `language`, so `wait_secs =
> "five"` or `initial_prompt = 42` would escape and explode later inside the
> daemon. The shipped module validates each optional field the way `config.py`
> validates the file (string for `initial_prompt`; positive number, `bool`
> rejected, for the two durations), and absent-or-null still means "not
> specified". `encode_reply`'s `match` also gained a `case _: assert_never(...)`
> so mypy fails the build if a fourth `Reply` variant is ever left unhandled.
> `decode_reply`'s key precedence (`status`, then `text`, then `error`) is now
> documented and tested. See commit `9bdcfd4`.

- [ ] **Step 1: Write the failing test**

`tests/test_ipc_protocol.py`:

```python
from __future__ import annotations

import pytest

from voxkey.ipc.protocol import (
    STATUS_RECORDING,
    DictationRequest,
    ErrorMessage,
    ProtocolError,
    ResultMessage,
    StatusMessage,
    decode_reply,
    decode_request,
    encode_reply,
    encode_request,
)


def test_request_round_trips() -> None:
    original = DictationRequest(
        language="fr", initial_prompt="Terms: a.", wait_secs=5.0, silence_secs=2.0
    )
    assert decode_request(encode_request(original)) == original


def test_request_defaults_are_filled_in() -> None:
    decoded = decode_request(b'{"language": "en"}')
    assert decoded.language == "en"
    assert decoded.initial_prompt is None
    assert decoded.wait_secs is None
    assert decoded.silence_secs is None


def test_malformed_request_is_reported() -> None:
    with pytest.raises(ProtocolError):
        decode_request(b"not json")


def test_status_reply_round_trips() -> None:
    assert decode_reply(encode_reply(StatusMessage(STATUS_RECORDING))) == StatusMessage(
        STATUS_RECORDING
    )


def test_result_reply_round_trips() -> None:
    assert decode_reply(encode_reply(ResultMessage("hello"))) == ResultMessage("hello")


def test_error_reply_round_trips() -> None:
    assert decode_reply(encode_reply(ErrorMessage("boom"))) == ErrorMessage("boom")


def test_every_reply_is_newline_terminated() -> None:
    for reply in (StatusMessage("recording"), ResultMessage("x"), ErrorMessage("y")):
        assert encode_reply(reply).endswith(b"\n")


def test_reply_without_a_known_field_is_reported() -> None:
    with pytest.raises(ProtocolError):
        decode_reply(b'{"unexpected": 1}')


def test_status_wire_shape_matches_dictate() -> None:
    assert encode_reply(StatusMessage("recording")) == b'{"status": "recording"}\n'
    assert encode_reply(ResultMessage("hi")) == b'{"text": "hi"}\n'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ipc_protocol.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.ipc'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/ipc/__init__.py`:

```python
"""The Unix socket between the resident daemon and its clients."""

from __future__ import annotations
```

`src/voxkey/ipc/protocol.py`:

```python
"""Messages exchanged over the Unix socket.

    client to daemon    one JSON object, then shutdown(SHUT_WR)
    daemon to client    newline delimited JSON objects

The wire shapes are unchanged from dictate, so an old client and a new daemon
still understand each other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

STATUS_RECORDING = "recording"
STATUS_TRANSCRIBING = "transcribing"


class ProtocolError(ValueError):
    """A message could not be understood."""


@dataclass(frozen=True)
class DictationRequest:
    language: str = "en"
    initial_prompt: str | None = None
    wait_secs: float | None = None
    silence_secs: float | None = None


@dataclass(frozen=True)
class StatusMessage:
    status: str


@dataclass(frozen=True)
class ResultMessage:
    text: str


@dataclass(frozen=True)
class ErrorMessage:
    message: str


Reply = StatusMessage | ResultMessage | ErrorMessage


def encode_request(request: DictationRequest) -> bytes:
    body: dict[str, object] = {"language": request.language}
    if request.initial_prompt is not None:
        body["initial_prompt"] = request.initial_prompt
    if request.wait_secs is not None:
        body["wait_secs"] = request.wait_secs
    if request.silence_secs is not None:
        body["silence_secs"] = request.silence_secs
    return json.dumps(body).encode()


def decode_request(payload: bytes) -> DictationRequest:
    try:
        body = json.loads(payload.decode() or "{}")
    except (ValueError, UnicodeDecodeError) as error:
        raise ProtocolError(f"unreadable request: {error}") from error
    if not isinstance(body, dict):
        raise ProtocolError("request must be a JSON object")
    return DictationRequest(
        language=str(body.get("language", "en")),
        initial_prompt=body.get("initial_prompt"),
        wait_secs=body.get("wait_secs"),
        silence_secs=body.get("silence_secs"),
    )


def encode_reply(reply: Reply) -> bytes:
    match reply:
        case StatusMessage(status):
            body: dict[str, str] = {"status": status}
        case ResultMessage(text):
            body = {"text": text}
        case ErrorMessage(message):
            body = {"error": message}
    return json.dumps(body).encode() + b"\n"


def decode_reply(payload: bytes) -> Reply:
    try:
        body = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError) as error:
        raise ProtocolError(f"unreadable reply: {error}") from error
    if not isinstance(body, dict):
        raise ProtocolError("reply must be a JSON object")
    if "status" in body:
        return StatusMessage(str(body["status"]))
    if "text" in body:
        return ResultMessage(str(body["text"]))
    if "error" in body:
        return ErrorMessage(str(body["error"]))
    raise ProtocolError(f"reply carries no known field: {sorted(body)}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ipc_protocol.py -v && ruff check . && mypy`
Expected: 9 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/ipc tests/test_ipc_protocol.py
git commit -m "Type the daemon protocol and test it without a socket

Requests and replies become dataclasses with pure serialisation, so the whole
message layer is covered before any socket exists."
```

---

### Task 8: `transcribe/base.py` and the fake

**Files:**
- Create: `src/voxkey/transcribe/__init__.py`
- Create: `src/voxkey/transcribe/base.py`
- Create: `tests/test_transcribe_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Transcriber` Protocol with `transcribe(audio: npt.NDArray[np.float32], language: str, initial_prompt: str | None) -> str`. `FakeTranscriber` recording its calls in `calls: list[tuple[str, str | None, int]]` and returning queued texts. Every later task that needs transcription depends on this Protocol, never on faster-whisper.

- [ ] **Step 1: Write the failing test**

`tests/test_transcribe_base.py`:

```python
from __future__ import annotations

import numpy as np

from voxkey.transcribe.base import FakeTranscriber, Transcriber


def test_fake_satisfies_the_protocol() -> None:
    transcriber: Transcriber = FakeTranscriber(["hello"])
    assert transcriber.transcribe(np.zeros(4, dtype=np.float32), "en", None) == "hello"


def test_fake_returns_queued_texts_in_order() -> None:
    transcriber = FakeTranscriber(["first", "second"])
    audio = np.zeros(4, dtype=np.float32)
    assert transcriber.transcribe(audio, "en", None) == "first"
    assert transcriber.transcribe(audio, "en", None) == "second"


def test_fake_repeats_the_last_text_once_the_queue_is_empty() -> None:
    transcriber = FakeTranscriber(["only"])
    audio = np.zeros(4, dtype=np.float32)
    assert transcriber.transcribe(audio, "en", None) == "only"
    assert transcriber.transcribe(audio, "en", None) == "only"


def test_fake_records_how_it_was_called() -> None:
    transcriber = FakeTranscriber(["x"])
    transcriber.transcribe(np.zeros(8, dtype=np.float32), "fr", "Terms: a.")
    assert transcriber.calls == [("fr", "Terms: a.", 8)]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_transcribe_base.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.transcribe'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/transcribe/__init__.py`:

```python
"""Turning recorded audio into text, locally or elsewhere."""

from __future__ import annotations
```

`src/voxkey/transcribe/base.py`:

```python
"""The transcription boundary.

Everything upstream of this Protocol is testable without a model, a GPU or a
network peer, which is the point: the daemon, the clients and the push-to-talk
state machine all depend on ``Transcriber`` and never on faster-whisper.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt


class Transcriber(Protocol):
    def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        language: str,
        initial_prompt: str | None,
    ) -> str:
        """Return the text spoken in ``audio``."""


class FakeTranscriber:
    """A Transcriber for tests. Returns queued texts and records its calls."""

    def __init__(self, texts: Sequence[str]) -> None:
        if not texts:
            raise ValueError("FakeTranscriber needs at least one text")
        self._texts = list(texts)
        self._index = 0
        self.calls: list[tuple[str, str | None, int]] = []

    def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        language: str,
        initial_prompt: str | None,
    ) -> str:
        self.calls.append((language, initial_prompt, len(audio)))
        text = self._texts[min(self._index, len(self._texts) - 1)]
        self._index += 1
        return text
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_transcribe_base.py -v && ruff check . && mypy`
Expected: 4 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/transcribe tests/test_transcribe_base.py
git commit -m "Put transcription behind a Protocol with a test double

Everything upstream of this boundary is now testable without a model, a GPU or
a network peer."
```

---

### Task 9: `transcribe/local.py`

**Files:**
- Create: `src/voxkey/transcribe/local.py`
- Create: `tests/test_transcribe_local.py`

**Interfaces:**
- Consumes: `voxkey.transcribe.base.Transcriber`.
- Produces: `pick_defaults(has_cuda: bool) -> ModelChoice`, `ModelChoice` dataclass with `device: str`, `compute_type: str`, `name: str`. `LocalTranscriber(model: object)` implementing `Transcriber`. `detect_cuda() -> bool`. `TRANSCRIBE_OPTIONS: dict[str, object]`.

- [ ] **Step 1: Write the failing test**

`tests/test_transcribe_local.py`:

```python
from __future__ import annotations

from typing import Any

import numpy as np

from voxkey.transcribe.local import (
    TRANSCRIBE_OPTIONS,
    LocalTranscriber,
    ModelChoice,
    pick_defaults,
)


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubModel:
    def __init__(self, segments: list[str]) -> None:
        self._segments = segments
        self.kwargs: dict[str, Any] = {}

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[_Segment], object]:
        self.kwargs = kwargs
        return [_Segment(text) for text in self._segments], object()


def test_cuda_selects_medium_int8() -> None:
    assert pick_defaults(has_cuda=True) == ModelChoice("cuda", "int8", "medium")


def test_cpu_selects_small_int8() -> None:
    assert pick_defaults(has_cuda=False) == ModelChoice("cpu", "int8", "small")


def test_segments_are_joined_and_stripped() -> None:
    model = _StubModel([" hello", " world "])
    assert LocalTranscriber(model).transcribe(
        np.zeros(4, dtype=np.float32), "en", None
    ) == "hello world"


def test_empty_result_is_the_empty_string() -> None:
    assert LocalTranscriber(_StubModel([])).transcribe(
        np.zeros(4, dtype=np.float32), "en", None
    ) == ""


def test_language_and_prompt_reach_the_model() -> None:
    model = _StubModel(["x"])
    LocalTranscriber(model).transcribe(np.zeros(4, dtype=np.float32), "fr", "Terms: a.")
    assert model.kwargs["language"] == "fr"
    assert model.kwargs["initial_prompt"] == "Terms: a."


def test_hallucination_guard_is_always_applied() -> None:
    model = _StubModel(["x"])
    LocalTranscriber(model).transcribe(np.zeros(4, dtype=np.float32), "en", None)
    assert model.kwargs["hallucination_silence_threshold"] == 2
    assert "hotwords" not in model.kwargs
    assert TRANSCRIBE_OPTIONS["hallucination_silence_threshold"] == 2
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_transcribe_local.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.transcribe.local'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/transcribe/local.py`:

```python
"""Transcription on this machine, through faster-whisper."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)

#: Options applied to every call.
#:
#: ``hallucination_silence_threshold`` stops Whisper inventing text over
#: silence. ``hotwords`` is deliberately absent: it degrades transcription when
#: many terms are supplied, which is why vocabulary goes through
#: ``initial_prompt`` instead.
TRANSCRIBE_OPTIONS: dict[str, object] = {
    "beam_size": 5,
    "vad_filter": True,
    "hallucination_silence_threshold": 2,
}


@dataclass(frozen=True)
class ModelChoice:
    device: str
    compute_type: str
    name: str


class _WhisperModel(Protocol):
    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, Any]: ...


def pick_defaults(has_cuda: bool) -> ModelChoice:
    """Choose a model sized for the hardware, as dictate did."""
    if has_cuda:
        return ModelChoice("cuda", "int8", "medium")
    return ModelChoice("cpu", "int8", "small")


def detect_cuda() -> bool:
    try:
        import ctranslate2
    except ImportError:
        return False
    try:
        return len(ctranslate2.get_supported_compute_types("cuda")) > 0
    except Exception:  # noqa: BLE001  # any ctranslate2 failure means no CUDA
        logger.debug("CUDA probe failed, falling back to CPU", exc_info=True)
        return False


def load_model(choice: ModelChoice) -> _WhisperModel:
    from faster_whisper import WhisperModel

    model: _WhisperModel = WhisperModel(
        choice.name, device=choice.device, compute_type=choice.compute_type
    )
    return model


class LocalTranscriber:
    """Transcriber backed by a resident faster-whisper model."""

    def __init__(self, model: _WhisperModel) -> None:
        self._model = model

    def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        language: str,
        initial_prompt: str | None,
    ) -> str:
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            initial_prompt=initial_prompt,
            **TRANSCRIBE_OPTIONS,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_transcribe_local.py -v && ruff check . && mypy`
Expected: 6 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/transcribe/local.py tests/test_transcribe_local.py
git commit -m "Transcribe locally through faster-whisper behind the Protocol

The hallucination guard and the deliberate absence of hotwords are now
enforced by a test rather than by a comment."
```

---

### Task 10: `transcribe/remote.py`

**Files:**
- Create: `src/voxkey/transcribe/remote.py`
- Create: `tests/test_transcribe_remote.py`

**Interfaces:**
- Consumes: `voxkey.net.tcp`, `voxkey.transcribe.base.Transcriber`.
- Produces: `parse_address(text: str) -> tuple[str, int]`, `RemoteTranscriber(address: tuple[str, int])` implementing `Transcriber`.

- [ ] **Step 1: Write the failing test**

`tests/test_transcribe_remote.py`:

```python
from __future__ import annotations

import socket
import threading
from typing import Iterator

import numpy as np
import pytest

from voxkey.net.tcp import RemoteError, decode_request, encode_error, encode_response
from voxkey.transcribe.remote import RemoteTranscriber, parse_address


@pytest.fixture
def echo_server() -> Iterator[tuple[tuple[str, int], list[str]]]:
    """A one-shot server that decodes the request and answers its language."""
    received: list[str] = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection, connection.makefile("rb") as stream:
            request = decode_request(stream)
            received.append(request.language)
            connection.sendall(encode_response(f"heard {len(request.audio)} samples"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    host, port = listener.getsockname()
    yield (host, port), received
    thread.join(timeout=5)
    listener.close()


def test_parse_address_splits_host_and_port() -> None:
    assert parse_address("192.168.1.10:5555") == ("192.168.1.10", 5555)


def test_parse_address_handles_ipv6_style_hosts() -> None:
    assert parse_address("::1:5555") == ("::1", 5555)


def test_parse_address_rejects_a_missing_port() -> None:
    with pytest.raises(ValueError, match="HOST:PORT"):
        parse_address("192.168.1.10")


def test_round_trip_against_a_real_socket(
    echo_server: tuple[tuple[str, int], list[str]],
) -> None:
    address, received = echo_server
    transcriber = RemoteTranscriber(address)
    text = transcriber.transcribe(np.zeros(3, dtype=np.float32), "fr", None)
    assert text == "heard 3 samples"
    assert received == ["fr"]


def test_server_error_surfaces_as_remote_error() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection, connection.makefile("rb") as stream:
            decode_request(stream)
            connection.sendall(encode_error("model exploded"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        transcriber = RemoteTranscriber(listener.getsockname())
        with pytest.raises(RemoteError, match="model exploded"):
            transcriber.transcribe(np.zeros(1, dtype=np.float32), "en", None)
    finally:
        thread.join(timeout=5)
        listener.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_transcribe_remote.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.transcribe.remote'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/transcribe/remote.py`:

```python
"""Transcription delegated to another machine on the local network."""

from __future__ import annotations

import socket

import numpy as np
import numpy.typing as npt

from voxkey.net.tcp import RemoteRequest, decode_response, encode_request

RECEIVE_CHUNK = 4096
CONNECT_TIMEOUT_SECS = 10.0


def parse_address(text: str) -> tuple[str, int]:
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ValueError(f"expected HOST:PORT, found {text!r}")
    return host, int(port)


class RemoteTranscriber:
    """Transcriber that ships the audio to a voxkey server and reads the text back."""

    def __init__(self, address: tuple[str, int]) -> None:
        self._address = address

    def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        language: str,
        initial_prompt: str | None,
    ) -> str:
        frame = encode_request(
            RemoteRequest(
                language=language,
                initial_prompt=initial_prompt or "",
                audio=np.asarray(audio, dtype=np.float32),
            )
        )
        with socket.create_connection(self._address, CONNECT_TIMEOUT_SECS) as connection:
            connection.sendall(frame)
            connection.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = connection.recv(RECEIVE_CHUNK)
                if not chunk:
                    break
                chunks.append(chunk)
        return decode_response(b"".join(chunks))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_transcribe_remote.py -v && ruff check . && mypy`
Expected: 5 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/transcribe/remote.py tests/test_transcribe_remote.py
git commit -m "Delegate transcription to a server on the local network

Tested against a real loopback socket rather than a mock, so the framing, the
half-close and the read loop are all exercised."
```

---

### Task 11: `audio/calibration.py`

**Files:**
- Create: `src/voxkey/audio/__init__.py`
- Create: `src/voxkey/audio/calibration.py`
- Create: `tests/test_calibration.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `rms(samples: npt.NDArray[np.float32]) -> float`, `threshold_from_ambient(ambient: float) -> float`, `retry_reason(ambient: float) -> str | None`, and the constants `SILENT_AMBIENT`, `NOISY_AMBIENT`, `MAX_THRESHOLD`, `MIN_THRESHOLD`, `CALIBRATION_SECS`, `DEFAULT_RETRIES`.

- [ ] **Step 1: Write the failing test**

`tests/test_calibration.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from voxkey.audio.calibration import (
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    retry_reason,
    rms,
    threshold_from_ambient,
)


def test_rms_of_silence_is_zero() -> None:
    assert rms(np.zeros(100, dtype=np.float32)) == 0.0


def test_rms_of_a_constant_signal_is_its_magnitude() -> None:
    assert rms(np.full(100, 0.5, dtype=np.float32)) == pytest.approx(0.5)


def test_rms_of_an_empty_buffer_is_zero() -> None:
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_threshold_is_ambient_and_a_half_plus_a_hundredth() -> None:
    assert threshold_from_ambient(0.01) == pytest.approx(0.025)


def test_threshold_is_capped() -> None:
    assert threshold_from_ambient(1.0) == MAX_THRESHOLD


def test_silence_yields_the_minimum_threshold() -> None:
    assert threshold_from_ambient(0.0) == pytest.approx(MIN_THRESHOLD)


def test_silence_asks_for_a_retry() -> None:
    assert retry_reason(0.0) == "silence"


def test_a_suspiciously_loud_reading_asks_for_a_retry() -> None:
    # PipeWire switching routes mid-calibration reads as a very loud room.
    assert retry_reason(0.5) == "noise"


def test_an_ordinary_room_does_not_ask_for_a_retry() -> None:
    assert retry_reason(0.005) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.audio'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/audio/__init__.py`:

```python
"""Capturing sound and deciding when speech starts and stops."""

from __future__ import annotations
```

`src/voxkey/audio/calibration.py`:

```python
"""Derive the speech threshold from a sample of the room.

The decisions live here as pure functions over a number, so every branch is
covered by a test with no microphone involved. Only the sampling itself, in
``capture``, touches a device.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

CALIBRATION_SECS = 0.5
DEFAULT_RETRIES = 5
RETRY_DELAY_SECS = 2.0

#: Below this the microphone is not delivering anything usable.
SILENT_AMBIENT = 0.001
#: Above this the reading is not a room, it is a device switching mid-sample.
NOISY_AMBIENT = 0.03

MIN_THRESHOLD = 0.01
MAX_THRESHOLD = 0.05


def rms(samples: npt.NDArray[np.float32]) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def threshold_from_ambient(ambient: float) -> float:
    """Speech threshold for a measured ambient level, capped for loud rooms."""
    return min(ambient * 1.5 + MIN_THRESHOLD, MAX_THRESHOLD)


def retry_reason(ambient: float) -> str | None:
    """Why this calibration should be thrown away, or None to accept it."""
    if ambient < SILENT_AMBIENT:
        return "silence"
    if ambient > NOISY_AMBIENT:
        return "noise"
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_calibration.py -v && ruff check . && mypy`
Expected: 9 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/audio tests/test_calibration.py
git commit -m "Extract microphone calibration into pure, tested decisions

The retry on a suspiciously loud reading is what catches PipeWire switching
routes mid-calibration, and it now has a test rather than a comment."
```

---

### Task 12: `audio/capture.py`

**Files:**
- Create: `src/voxkey/audio/capture.py`
- Create: `tests/test_capture.py`

**Interfaces:**
- Consumes: `voxkey.audio.calibration.rms`.
- Produces: `AudioSource` Protocol with `blocks() -> Iterator[npt.NDArray[np.float32]]`. `SyntheticAudioSource(blocks, block_secs)` for tests. `SilenceDetector(threshold, silence_secs, wait_secs)` with `feed(level: float, now: float) -> bool` and properties `speech_detected: bool`, `finished: bool`. `PreBuffer(max_secs, sample_rate)` with `append`, `drain`. `record_utterance(source, detector, clock, stop_flag=None) -> npt.NDArray[np.float32] | None`, named so it never reads as the `Recorder.record` method introduced in Task 16. Constant `SAMPLE_RATE = 16000`.

- [ ] **Step 1: Write the failing test**

`tests/test_capture.py`:

```python
from __future__ import annotations

import numpy as np

from voxkey.audio.capture import (
    SAMPLE_RATE,
    PreBuffer,
    SilenceDetector,
    SyntheticAudioSource,
    record_utterance,
)


def test_detector_stops_after_silence_that_follows_speech() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    assert detector.feed(0.5, now=0.0) is True
    assert detector.feed(0.0, now=1.0) is True
    assert detector.feed(0.0, now=2.9) is True
    assert detector.feed(0.0, now=3.1) is False
    assert detector.speech_detected is True


def test_silence_timer_restarts_on_new_speech() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    detector.feed(0.5, now=0.0)
    detector.feed(0.0, now=2.0)
    detector.feed(0.5, now=2.5)
    assert detector.feed(0.0, now=5.0) is True


def test_detector_gives_up_when_no_speech_ever_arrives() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    assert detector.feed(0.0, now=5.0) is True
    assert detector.feed(0.0, now=10.1) is False
    assert detector.speech_detected is False


def test_a_level_exactly_at_the_threshold_is_not_speech() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    detector.feed(0.1, now=0.0)
    assert detector.speech_detected is False


def test_prebuffer_keeps_only_the_last_second() -> None:
    buffer = PreBuffer(max_secs=1.0, sample_rate=10)
    for value in range(15):
        buffer.append(np.full(1, float(value), dtype=np.float32))
    drained = buffer.drain()
    assert len(drained) == 10
    assert drained[0] == 5.0
    assert drained[-1] == 14.0


def test_prebuffer_drain_empties_it() -> None:
    buffer = PreBuffer(max_secs=1.0, sample_rate=10)
    buffer.append(np.ones(3, dtype=np.float32))
    buffer.drain()
    assert len(buffer.drain()) == 0


def test_record_returns_the_spoken_audio() -> None:
    source = SyntheticAudioSource(
        [
            np.full(160, 0.5, dtype=np.float32),
            np.full(160, 0.5, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
        ],
        block_secs=1.0,
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    audio = record_utterance(source, detector, clock=source.clock)
    assert audio is not None
    assert len(audio) == 5 * 160


def test_record_returns_none_when_nothing_was_said() -> None:
    source = SyntheticAudioSource(
        [np.zeros(160, dtype=np.float32) for _ in range(12)], block_secs=1.0
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    assert record_utterance(source, detector, clock=source.clock) is None


def test_record_stops_when_the_stop_flag_is_raised() -> None:
    source = SyntheticAudioSource(
        [np.full(160, 0.5, dtype=np.float32) for _ in range(10)], block_secs=1.0
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    calls = {"count": 0}

    def stop_flag() -> bool:
        calls["count"] += 1
        return calls["count"] >= 3

    audio = record_utterance(
        source, detector, clock=source.clock, stop_flag=stop_flag
    )
    assert audio is not None
    assert len(audio) == 3 * 160


def test_sample_rate_is_the_one_whisper_expects() -> None:
    assert SAMPLE_RATE == 16000
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_capture.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.audio.capture'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/audio/capture.py`:

```python
"""Recording, and deciding when to stop.

dictate made this decision inside a PortAudio callback closing over four
mutable variables, which cannot be tested. Here the decision is a state machine
fed one level at a time, and the device is a Protocol.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt

from voxkey.audio.calibration import rms

SAMPLE_RATE = 16000
BLOCK_SECS = 0.1


class AudioSource(Protocol):
    def blocks(self) -> Iterator[npt.NDArray[np.float32]]:
        """Yield successive blocks of mono float32 samples."""


class SyntheticAudioSource:
    """An AudioSource for tests, with a clock that advances one block at a time."""

    def __init__(
        self, blocks: Sequence[npt.NDArray[np.float32]], block_secs: float = BLOCK_SECS
    ) -> None:
        self._blocks = list(blocks)
        self._block_secs = block_secs
        self._elapsed = 0.0

    def blocks(self) -> Iterator[npt.NDArray[np.float32]]:
        for block in self._blocks:
            yield block
            self._elapsed += self._block_secs

    def clock(self) -> float:
        return self._elapsed


class SilenceDetector:
    """Decide, level by level, whether recording should continue."""

    def __init__(self, threshold: float, silence_secs: float, wait_secs: float) -> None:
        self._threshold = threshold
        self._silence_secs = silence_secs
        self._wait_secs = wait_secs
        self._started: float | None = None
        self._last_speech = 0.0
        self.speech_detected = False
        self.finished = False

    def feed(self, level: float, now: float) -> bool:
        """Return True to keep recording, False to stop."""
        if self._started is None:
            self._started = now
            self._last_speech = now
        if level > self._threshold:
            self.speech_detected = True
            self._last_speech = now
            return True
        if self.speech_detected:
            if now - self._last_speech >= self._silence_secs:
                self.finished = True
                return False
            return True
        if now - self._started >= self._wait_secs:
            self.finished = True
            return False
        return True


class PreBuffer:
    """A rolling window of the most recent audio.

    This is what removes the delay at the start of a dictation: the words
    spoken before recording actually begins are already in here.
    """

    def __init__(self, max_secs: float, sample_rate: int = SAMPLE_RATE) -> None:
        self._samples: deque[float] = deque(maxlen=int(max_secs * sample_rate))

    def append(self, block: npt.NDArray[np.float32]) -> None:
        self._samples.extend(block.tolist())

    def drain(self) -> npt.NDArray[np.float32]:
        drained: npt.NDArray[np.float32] = np.array(self._samples, dtype=np.float32)
        self._samples.clear()
        return drained


def record_utterance(
    source: AudioSource,
    detector: SilenceDetector,
    clock: Callable[[], float],
    stop_flag: Callable[[], bool] | None = None,
) -> npt.NDArray[np.float32] | None:
    """Record until the detector says stop, or the stop flag is raised.

    Returns None when no speech was ever heard, which the caller reports rather
    than sending an empty buffer to the model.
    """
    collected: list[npt.NDArray[np.float32]] = []
    for block in source.blocks():
        collected.append(block)
        if stop_flag is not None and stop_flag():
            # A manual stop is a valid recording, whatever the levels were.
            detector.speech_detected = True
            break
        if not detector.feed(rms(block), clock()):
            break
    if not collected or not detector.speech_detected:
        return None
    return np.concatenate(collected).astype(np.float32)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_capture.py -v && ruff check . && mypy`
Expected: 10 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/audio/capture.py tests/test_capture.py
git commit -m "Make the stop decision a testable state machine

dictate decided when to stop inside a PortAudio callback closing over four
mutable variables, which no test could reach. The decision now takes one level
at a time and the device is a Protocol."
```

---

### Task 13: `audio/devices.py`

**Files:**
- Create: `src/voxkey/audio/devices.py`
- Create: `tests/test_devices.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DeviceInfo` dataclass with `index: int`, `name: str`, `max_input_channels: int`. `choose_input_device(devices: Sequence[DeviceInfo]) -> int | None`, `list_input_devices() -> list[DeviceInfo]`, `StreamAudioSource(device, block_secs)` implementing `AudioSource`.

- [ ] **Step 1: Write the failing test**

`tests/test_devices.py`:

```python
from __future__ import annotations

from voxkey.audio.devices import DeviceInfo, choose_input_device


def _device(index: int, name: str, inputs: int = 1) -> DeviceInfo:
    return DeviceInfo(index=index, name=name, max_input_channels=inputs)


def test_pipewire_is_preferred_over_default() -> None:
    # The ALSA "default" device does not route a Bluetooth microphone
    # correctly, so the PipeWire device is chosen by name.
    devices = [_device(0, "default"), _device(1, "pipewire")]
    assert choose_input_device(devices) == 1


def test_pipewire_match_is_case_insensitive() -> None:
    assert choose_input_device([_device(0, "default"), _device(3, "PipeWire")]) == 3


def test_first_input_capable_device_when_no_pipewire() -> None:
    devices = [_device(0, "speakers", inputs=0), _device(1, "usb mic")]
    assert choose_input_device(devices) == 1


def test_output_only_devices_are_never_chosen() -> None:
    assert choose_input_device([_device(0, "hdmi out", inputs=0)]) is None


def test_no_devices_at_all_yields_none() -> None:
    assert choose_input_device([]) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_devices.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.audio.devices'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/audio/devices.py`:

```python
"""Finding a microphone.

Selection is a pure function over a list of descriptions, so the preference
rules are tested without any sound card present. Only ``list_input_devices``
and ``StreamAudioSource`` touch PortAudio.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from voxkey.audio.capture import BLOCK_SECS, SAMPLE_RATE

PREFERRED_NAME = "pipewire"


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    max_input_channels: int


def choose_input_device(devices: Sequence[DeviceInfo]) -> int | None:
    """Prefer PipeWire by name, then the first device that can record."""
    inputs = [device for device in devices if device.max_input_channels > 0]
    for device in inputs:
        if PREFERRED_NAME in device.name.casefold():
            return device.index
    return inputs[0].index if inputs else None


def list_input_devices() -> list[DeviceInfo]:
    import sounddevice

    found: list[DeviceInfo] = []
    for index, raw in enumerate(sounddevice.query_devices()):
        found.append(
            DeviceInfo(
                index=index,
                name=str(raw["name"]),
                max_input_channels=int(raw["max_input_channels"]),
            )
        )
    return found


class StreamAudioSource:
    """AudioSource backed by a real PortAudio input stream."""

    def __init__(self, device: int | None, block_secs: float = BLOCK_SECS) -> None:
        self._device = device
        self._block_frames = int(SAMPLE_RATE * block_secs)

    def blocks(self) -> Iterator[npt.NDArray[np.float32]]:
        import sounddevice

        with sounddevice.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self._device,
            blocksize=self._block_frames,
        ) as stream:
            while True:
                frames, _overflowed = stream.read(self._block_frames)
                block: npt.NDArray[np.float32] = np.asarray(
                    frames, dtype=np.float32
                ).flatten()
                yield block
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_devices.py -v && ruff check . && mypy`
Expected: 5 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/audio/devices.py tests/test_devices.py
git commit -m "Choose the microphone by rules that a test can check

Preferring the PipeWire device over the ALSA default is what makes a Bluetooth
microphone route correctly, and it is now a pure function over a device list."
```

---

### Task 14: `output/clipboard.py` and `output/sound.py`

**Files:**
- Create: `src/voxkey/output/__init__.py`
- Create: `src/voxkey/output/clipboard.py`
- Create: `src/voxkey/output/sound.py`
- Create: `tests/test_output.py`

**Interfaces:**
- Consumes: `voxkey.state.sound_enabled`.
- Produces: `clipboard.copy(text: str, runner: Runner | None = None) -> bool`, `clipboard.CLIPBOARD_COMMAND: list[str]`. `sound.build_command(player: str, path: Path) -> list[str]`, `sound.child_environment(base: Mapping[str, str]) -> dict[str, str]`, `sound.play(path, spawner=None) -> bool`, `sound.PLAYERS: tuple[str, ...]`, `sound.VOLUME: str`, `sound.SOUND_COMPLETE: Path`, `sound.SOUND_BELL: Path`. Type alias `Runner = Callable[[list[str], bytes], int]`.

- [ ] **Step 1: Write the failing test**

`tests/test_output.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from voxkey import state
from voxkey.output import clipboard, sound


def test_clipboard_uses_xsel_not_wl_copy() -> None:
    # wtype does not work under GNOME Wayland, and xsel is focus independent.
    assert clipboard.CLIPBOARD_COMMAND[0] == "xsel"


def test_clipboard_sends_the_text_on_stdin() -> None:
    seen: list[tuple[list[str], bytes]] = []

    def runner(command: list[str], payload: bytes) -> int:
        seen.append((command, payload))
        return 0

    assert clipboard.copy("hello", runner=runner) is True
    assert seen[0][1] == b"hello"


def test_clipboard_reports_failure() -> None:
    assert clipboard.copy("hello", runner=lambda command, payload: 1) is False


def test_sound_command_carries_the_volume() -> None:
    command = sound.build_command("pw-play", Path("/tmp/a.oga"))
    assert command == ["pw-play", f"--volume={sound.VOLUME}", "/tmp/a.oga"]


def test_players_without_a_volume_flag_get_a_bare_command() -> None:
    assert sound.build_command("paplay", Path("/tmp/a.oga")) == ["paplay", "/tmp/a.oga"]


def test_child_environment_forces_the_c_numeric_locale() -> None:
    # pw-play parses --volume with strtof, which honours LC_NUMERIC. Under a
    # comma-decimal locale "0.5" stops at the dot and becomes zero, i.e.
    # silence. Any float handed to a C binary as an argument needs this.
    environment = sound.child_environment({"LC_NUMERIC": "fr_FR.UTF-8", "HOME": "/h"})
    assert environment["LC_NUMERIC"] == "C"
    assert environment["HOME"] == "/h"


def test_child_environment_sets_the_locale_even_when_it_was_unset() -> None:
    assert sound.child_environment({})["LC_NUMERIC"] == "C"


def test_play_is_silent_when_the_tray_muted_it(xdg: Path, tmp_path: Path) -> None:
    state.set_sound_enabled(False)
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    spawned: list[list[str]] = []
    assert sound.play(target, spawner=lambda c, e: spawned.append(c)) is False
    assert spawned == []


def test_play_is_silent_when_the_file_is_missing(xdg: Path, tmp_path: Path) -> None:
    spawned: list[list[str]] = []
    result = sound.play(tmp_path / "absent.oga", spawner=lambda c, e: spawned.append(c))
    assert result is False
    assert spawned == []


def test_play_falls_back_to_the_next_player(xdg: Path, tmp_path: Path) -> None:
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    attempted: list[str] = []

    def spawner(command: list[str], environment: dict[str, str]) -> None:
        attempted.append(command[0])
        if command[0] != "canberra-gtk-play":
            raise FileNotFoundError(command[0])

    assert sound.play(target, spawner=spawner) is True
    assert attempted == list(sound.PLAYERS)


def test_play_passes_the_forced_locale_to_the_child(xdg: Path, tmp_path: Path) -> None:
    target = tmp_path / "a.oga"
    target.write_bytes(b"")
    captured: dict[str, str] = {}

    def spawner(command: list[str], environment: dict[str, str]) -> None:
        captured.update(environment)

    sound.play(target, spawner=spawner)
    assert captured["LC_NUMERIC"] == "C"
    assert "PATH" in captured or "PATH" not in os.environ
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_output.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.output'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/output/__init__.py`:

```python
"""Where the transcribed text and the notification sounds go."""

from __future__ import annotations
```

`src/voxkey/output/clipboard.py`:

```python
"""Putting the transcribed text where it can be pasted.

``xsel`` rather than ``wl-copy``: ``wtype`` does not work under GNOME Wayland,
and ``xsel`` is focus independent, which matters because the dictation ends
while the focus is wherever the user left it.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

logger = logging.getLogger(__name__)

CLIPBOARD_COMMAND = ["xsel", "--clipboard", "--input"]

Runner = Callable[[list[str], bytes], int]


def _run(command: list[str], payload: bytes) -> int:
    process = subprocess.run(command, input=payload, check=False)
    return process.returncode


def copy(text: str, runner: Runner | None = None) -> bool:
    """Copy ``text`` to the clipboard. Returns whether it worked."""
    execute = runner if runner is not None else _run
    try:
        code = execute(CLIPBOARD_COMMAND, text.encode())
    except FileNotFoundError:
        logger.error("xsel is not installed, cannot reach the clipboard")
        return False
    if code != 0:
        logger.error("xsel exited with %s", code)
        return False
    return True
```

`src/voxkey/output/sound.py`:

```python
"""Short notification sounds.

The whole reason this module has a ``child_environment`` function: ``pw-play``
parses ``--volume`` with ``strtof``, which honours ``LC_NUMERIC``. On a machine
using a comma decimal separator, "0.5" stops at the dot and becomes zero, so
the sound plays at silence. Any float handed to a C binary as an argument needs
the same treatment.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from voxkey import state

logger = logging.getLogger(__name__)

SOUND_COMPLETE = Path("/usr/share/sounds/freedesktop/stereo/message.oga")
SOUND_BELL = Path("/usr/share/sounds/freedesktop/stereo/dialog-warning.oga")

VOLUME = "0.5"
PLAYERS = ("pw-play", "paplay", "canberra-gtk-play")

Spawner = Callable[[list[str], dict[str, str]], None]


def build_command(player: str, path: Path) -> list[str]:
    if player == "pw-play":
        return [player, f"--volume={VOLUME}", str(path)]
    if player == "canberra-gtk-play":
        return [player, "-f", str(path)]
    return [player, str(path)]


def child_environment(base: Mapping[str, str]) -> dict[str, str]:
    """The child's environment, with the numeric locale forced to C."""
    return {**base, "LC_NUMERIC": "C"}


def _spawn(command: list[str], environment: dict[str, str]) -> None:
    subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def play(path: Path, spawner: Spawner | None = None) -> bool:
    """Play a sound unless muted or missing. Returns whether a player started."""
    if not state.sound_enabled() or not path.exists():
        return False
    launch = spawner if spawner is not None else _spawn
    environment = child_environment(os.environ)
    for player in PLAYERS:
        try:
            launch(build_command(player, path), environment)
        except FileNotFoundError:
            continue
        else:
            return True
    logger.warning("no audio player available, tried %s", ", ".join(PLAYERS))
    return False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_output.py -v && ruff check . && mypy`
Expected: 11 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/output tests/test_output.py
git commit -m "Copy through xsel and play sounds under a forced C numeric locale

pw-play parses --volume with strtof, so a comma-decimal locale turned 0.5 into
zero and the sound never played. The forced locale is now a tested function
rather than a line inside a spawn call."
```

---

### Task 15: `ptt/` push-to-talk

**Files:**
- Create: `src/voxkey/ptt/__init__.py`
- Create: `src/voxkey/ptt/machine.py`
- Create: `src/voxkey/ptt/keyboard.py`
- Create: `tests/test_ptt_machine.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `KeyEvent` dataclass with `pressed: bool`, `timestamp: float`. `HoldDecision` enum with `START`, `ACCEPT`, `DISCARD`, `IGNORE`. `HoldMachine(min_hold_secs)` with `feed(event: KeyEvent) -> HoldDecision` and property `holding: bool`. Constant `MIN_HOLD_SECS = 1.0`. `keyboard.find_keyboards() -> list[str]`, `keyboard.key_events(device_path, key_code) -> Iterator[KeyEvent]`, `keyboard.resolve_key(name: str) -> int`.

- [ ] **Step 1: Write the failing test**

`tests/test_ptt_machine.py`:

```python
from __future__ import annotations

from voxkey.ptt.machine import MIN_HOLD_SECS, HoldDecision, HoldMachine, KeyEvent


def test_a_genuine_dictation_is_accepted() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    assert machine.feed(KeyEvent(pressed=True, timestamp=0.0)) is HoldDecision.START
    assert machine.feed(KeyEvent(pressed=False, timestamp=2.0)) is HoldDecision.ACCEPT


def test_a_phantom_press_is_discarded() -> None:
    # RIGHTCTRL is also the paste modifier, so every Ctrl+V retriggers a
    # recording. Measured: every press under 0.6 s was a phantom, and the
    # shortest genuine dictation was 2.0 s.
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=0.4)) is HoldDecision.DISCARD


def test_the_boundary_is_inclusive() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=1.0)) is HoldDecision.ACCEPT


def test_a_repeat_while_already_held_is_ignored() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=True, timestamp=0.5)) is HoldDecision.IGNORE


def test_a_release_without_a_press_is_ignored() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    assert machine.feed(KeyEvent(pressed=False, timestamp=1.0)) is HoldDecision.IGNORE


def test_holding_reflects_the_current_state() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    assert machine.holding is False
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.holding is True
    machine.feed(KeyEvent(pressed=False, timestamp=2.0))
    assert machine.holding is False


def test_a_phantom_then_a_genuine_press_both_behave() -> None:
    machine = HoldMachine(min_hold_secs=1.0)
    machine.feed(KeyEvent(pressed=True, timestamp=0.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=0.2)) is HoldDecision.DISCARD
    machine.feed(KeyEvent(pressed=True, timestamp=5.0))
    assert machine.feed(KeyEvent(pressed=False, timestamp=8.0)) is HoldDecision.ACCEPT


def test_the_default_minimum_hold_is_one_second() -> None:
    assert MIN_HOLD_SECS == 1.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ptt_machine.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.ptt'`.

- [ ] **Step 3: Write the state machine**

`src/voxkey/ptt/__init__.py`:

```python
"""Reading the push-to-talk key and turning holds into dictations."""

from __future__ import annotations
```

`src/voxkey/ptt/machine.py`:

```python
"""When a key hold counts as a dictation.

The push-to-talk key is also a modifier. With the RIGHTCTRL default, every
Ctrl+V paste retriggers a recording; those phantom presses last a few tenths of
a second, and Whisper fills the silence with subtitle boilerplate, which then
overwrites the clipboard the paste had just consumed.

A phrase blacklist is not enough, because observed hallucinations include text
that is not on any list. The duration is the reliable signal: every measured
press under 0.6 s was a phantom, and the shortest genuine dictation was 2.0 s.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

MIN_HOLD_SECS = 1.0


@dataclass(frozen=True)
class KeyEvent:
    pressed: bool
    timestamp: float


class HoldDecision(Enum):
    START = auto()
    ACCEPT = auto()
    DISCARD = auto()
    IGNORE = auto()


class HoldMachine:
    """Turn a stream of key events into start, accept and discard decisions."""

    def __init__(self, min_hold_secs: float = MIN_HOLD_SECS) -> None:
        self._min_hold_secs = min_hold_secs
        self._pressed_at: float | None = None

    @property
    def holding(self) -> bool:
        return self._pressed_at is not None

    def feed(self, event: KeyEvent) -> HoldDecision:
        if event.pressed:
            if self._pressed_at is not None:
                return HoldDecision.IGNORE
            self._pressed_at = event.timestamp
            return HoldDecision.START
        if self._pressed_at is None:
            return HoldDecision.IGNORE
        held_for = event.timestamp - self._pressed_at
        self._pressed_at = None
        if held_for >= self._min_hold_secs:
            return HoldDecision.ACCEPT
        return HoldDecision.DISCARD
```

- [ ] **Step 4: Write the evdev shell**

`src/voxkey/ptt/keyboard.py`:

```python
"""Reading the keyboard through evdev.

This module is a thin shell around a device that a test cannot open. Every
decision it might have made lives in ``machine`` instead.

Reading /dev/input/event* requires membership of the ``input`` group. The
desktop session does not carry that group, which is why the systemd unit wraps
the command in ``sg input -c``. Without the wrapper this exits immediately with
"no keyboard found".
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from voxkey.ptt.machine import KeyEvent

logger = logging.getLogger(__name__)


class NoKeyboardError(RuntimeError):
    """No readable keyboard was found. Usually the missing input group."""


def resolve_key(name: str) -> int:
    """Turn a key name without its KEY_ prefix into an evdev code."""
    from evdev import ecodes

    code = getattr(ecodes, f"KEY_{name.upper()}", None)
    if code is None:
        raise ValueError(f"unknown key name: {name}")
    return int(code)


def find_keyboards() -> list[str]:
    """Device paths that look like a real keyboard."""
    import evdev
    from evdev import ecodes

    found: list[str] = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        capabilities = device.capabilities()
        keys = capabilities.get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys and ecodes.KEY_ENTER in keys:
            found.append(path)
    if not found:
        raise NoKeyboardError(
            "no keyboard found. Check membership of the input group, and that "
            "the service runs through the sg input wrapper."
        )
    return found


def key_events(device_path: str, key_code: int) -> Iterator[KeyEvent]:
    """Yield press and release events for one key on one device."""
    import evdev
    from evdev import ecodes

    device = evdev.InputDevice(device_path)
    for event in device.read_loop():
        if event.type != ecodes.EV_KEY or event.code != key_code:
            continue
        if event.value == 1:
            yield KeyEvent(pressed=True, timestamp=event.timestamp())
        elif event.value == 0:
            yield KeyEvent(pressed=False, timestamp=event.timestamp())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ptt_machine.py -v && ruff check . && mypy`
Expected: 8 passed, clean.

- [ ] **Step 6: Commit**

```bash
git add src/voxkey/ptt tests/test_ptt_machine.py
git commit -m "Reject phantom key presses through a tested state machine

Every Ctrl+V paste retriggers the push-to-talk key, and Whisper turns those
tenths of a second of silence into subtitle boilerplate that overwrites the
clipboard. The minimum hold now has tests at its boundary instead of a
constant and a comment."
```

---

### Task 16: `ipc/server.py`, the daemon

**Files:**
- Create: `src/voxkey/ipc/server.py`
- Create: `tests/test_ipc_server.py`

**Interfaces:**
- Consumes: `voxkey.ipc.protocol`, `voxkey.transcribe.base.Transcriber`, `voxkey.audio.capture`, `voxkey.state`.
- Produces: `Recorder` Protocol with `record(wait_secs: float, silence_secs: float) -> npt.NDArray[np.float32] | None`. `FakeRecorder(clips)`. `Daemon(transcriber, recorder, socket_path, config)` with `serve_forever() -> None`, `handle(connection) -> None`, `stop() -> None`. `run_daemon(...) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/test_ipc_server.py`:

```python
from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Iterator

import numpy as np
import pytest

from voxkey.config import Config
from voxkey.ipc.protocol import (
    STATUS_RECORDING,
    STATUS_TRANSCRIBING,
    DictationRequest,
    ErrorMessage,
    ResultMessage,
    StatusMessage,
    decode_reply,
    encode_request,
)
from voxkey.ipc.server import Daemon, FakeRecorder
from voxkey.transcribe.base import FakeTranscriber


@pytest.fixture
def daemon(xdg: Path, tmp_path: Path) -> Iterator[tuple[Daemon, Path, FakeTranscriber]]:
    socket_path = tmp_path / "voxkey.sock"
    transcriber = FakeTranscriber(["transcribed text"])
    recorder = FakeRecorder([np.ones(160, dtype=np.float32)])
    instance = Daemon(
        transcriber=transcriber,
        recorder=recorder,
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    for _ in range(200):
        if socket_path.exists():
            break
        threading.Event().wait(0.01)
    yield instance, socket_path, transcriber
    instance.stop()
    thread.join(timeout=5)


def _dictate(socket_path: Path, request: DictationRequest) -> list[object]:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))
    with client:
        client.sendall(encode_request(request))
        client.shutdown(socket.SHUT_WR)
        buffer = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            buffer += chunk
    return [decode_reply(line) for line in buffer.splitlines() if line.strip()]


def test_the_socket_is_created(daemon: tuple[Daemon, Path, FakeTranscriber]) -> None:
    _instance, socket_path, _transcriber = daemon
    assert socket_path.exists()


def test_a_dictation_streams_status_then_text(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, _transcriber = daemon
    replies = _dictate(socket_path, DictationRequest(language="en"))
    assert replies == [
        StatusMessage(STATUS_RECORDING),
        StatusMessage(STATUS_TRANSCRIBING),
        ResultMessage("transcribed text"),
    ]


def test_the_request_language_reaches_the_transcriber(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, transcriber = daemon
    _dictate(socket_path, DictationRequest(language="fr", initial_prompt="Terms: a."))
    assert transcriber.calls == [("fr", "Terms: a.", 160)]


def test_silence_is_reported_rather_than_transcribed(xdg: Path, tmp_path: Path) -> None:
    socket_path = tmp_path / "silent.sock"
    transcriber = FakeTranscriber(["should not be called"])
    instance = Daemon(
        transcriber=transcriber,
        recorder=FakeRecorder([None]),
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    for _ in range(200):
        if socket_path.exists():
            break
        threading.Event().wait(0.01)
    try:
        replies = _dictate(socket_path, DictationRequest())
        assert replies[-1] == ResultMessage("")
        assert transcriber.calls == []
    finally:
        instance.stop()
        thread.join(timeout=5)


def test_a_malformed_request_yields_an_error_reply(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, _transcriber = daemon
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))
    with client:
        client.sendall(b"not json")
        client.shutdown(socket.SHUT_WR)
        buffer = client.recv(4096)
    assert isinstance(decode_reply(buffer.strip()), ErrorMessage)


def test_two_dictations_in_a_row_both_work(
    daemon: tuple[Daemon, Path, FakeTranscriber],
) -> None:
    _instance, socket_path, _transcriber = daemon
    first = _dictate(socket_path, DictationRequest())
    second = _dictate(socket_path, DictationRequest())
    assert first[-1] == ResultMessage("transcribed text")
    assert second[-1] == ResultMessage("transcribed text")


def test_a_stale_socket_file_is_replaced(xdg: Path, tmp_path: Path) -> None:
    socket_path = tmp_path / "stale.sock"
    socket_path.write_text("not a socket")
    instance = Daemon(
        transcriber=FakeTranscriber(["x"]),
        recorder=FakeRecorder([np.ones(16, dtype=np.float32)]),
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if socket_path.is_socket():
                break
            threading.Event().wait(0.01)
        assert socket_path.is_socket()
    finally:
        instance.stop()
        thread.join(timeout=5)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ipc_server.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.ipc.server'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/ipc/server.py`:

```python
"""The resident daemon.

It exists so the Whisper model is loaded once rather than per dictation, and so
the push-to-talk client can be restarted freely without paying for a reload.
One request is served at a time: there is one microphone.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from voxkey import state
from voxkey.config import Config
from voxkey.ipc.protocol import (
    STATUS_RECORDING,
    STATUS_TRANSCRIBING,
    ErrorMessage,
    ProtocolError,
    Reply,
    ResultMessage,
    StatusMessage,
    decode_request,
    encode_reply,
)
from voxkey.transcribe.base import Transcriber

logger = logging.getLogger(__name__)

RECEIVE_CHUNK = 4096
ACCEPT_TIMEOUT_SECS = 0.2


class Recorder(Protocol):
    def record(
        self, wait_secs: float, silence_secs: float
    ) -> npt.NDArray[np.float32] | None:
        """Record one utterance, or return None when nothing was said."""


class FakeRecorder:
    """A Recorder for tests. Returns queued clips, or None for silence."""

    def __init__(self, clips: Sequence[npt.NDArray[np.float32] | None]) -> None:
        self._clips = list(clips)
        self._index = 0

    def record(
        self, wait_secs: float, silence_secs: float
    ) -> npt.NDArray[np.float32] | None:
        clip = self._clips[min(self._index, len(self._clips) - 1)]
        self._index += 1
        return clip


class Daemon:
    def __init__(
        self,
        transcriber: Transcriber,
        recorder: Recorder,
        socket_path: Path,
        config: Config,
    ) -> None:
        self._transcriber = transcriber
        self._recorder = recorder
        self._socket_path = socket_path
        self._config = config
        self._stopping = threading.Event()

    def _bind(self) -> socket.socket:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # A crash leaves the socket file behind and bind would fail on it.
        self._socket_path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self._socket_path))
        listener.listen(1)
        listener.settimeout(ACCEPT_TIMEOUT_SECS)
        return listener

    def serve_forever(self) -> None:
        listener = self._bind()
        state.set_state(state.STATE_IDLE)
        try:
            while not self._stopping.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    self.handle(connection)
        finally:
            listener.close()
            self._socket_path.unlink(missing_ok=True)
            state.set_state(state.STATE_OFF)

    def stop(self) -> None:
        self._stopping.set()

    def _send(self, connection: socket.socket, reply: Reply) -> None:
        connection.sendall(encode_reply(reply))

    def handle(self, connection: socket.socket) -> None:
        payload = b""
        while True:
            chunk = connection.recv(RECEIVE_CHUNK)
            if not chunk:
                break
            payload += chunk
        try:
            request = decode_request(payload)
        except ProtocolError as error:
            logger.warning("rejected a request: %s", error)
            self._send(connection, ErrorMessage(str(error)))
            return

        try:
            self._send(connection, StatusMessage(STATUS_RECORDING))
            state.set_state(state.STATE_RECORDING)
            audio = self._recorder.record(
                wait_secs=request.wait_secs or self._config.wait_secs,
                silence_secs=request.silence_secs or self._config.silence_secs,
            )
            if audio is None:
                logger.info("no speech detected")
                state.set_state(state.STATE_IDLE)
                self._send(connection, ResultMessage(""))
                return

            self._send(connection, StatusMessage(STATUS_TRANSCRIBING))
            state.set_state(state.STATE_TRANSCRIBING)
            text = self._transcriber.transcribe(
                audio, request.language, request.initial_prompt
            )
            if self._config.log_transcripts:
                logger.info("transcribed: %s", text)
            else:
                logger.info("transcribed %d characters", len(text))
            state.set_state(state.STATE_DONE)
            self._send(connection, ResultMessage(text))
        except Exception as error:  # noqa: BLE001  # one bad request must not kill the daemon
            logger.exception("dictation failed")
            state.set_state(state.STATE_ERROR)
            self._send(connection, ErrorMessage(str(error)))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ipc_server.py -v && ruff check . && mypy`
Expected: 7 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/ipc/server.py tests/test_ipc_server.py
git commit -m "Serve dictations from a resident daemon over a Unix socket

Tested end to end on a real socket with a fake microphone and a fake model, so
the accept loop, the half-close and the reply stream are all exercised without
any hardware. Transcript logging stays off by default and records a length."
```

---

### Task 17: `runtime.py`, wiring the daemon to real hardware

**Files:**
- Create: `src/voxkey/runtime.py`
- Create: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `voxkey.audio.*`, `voxkey.transcribe.*`, `voxkey.ipc.server.Daemon`, `voxkey.config.Config`, `voxkey.paths`.
- Produces: `StreamRecorder(device: int | None, config: Config)` implementing `Recorder`. `build_transcriber(config: Config) -> Transcriber`. `run_tcp_server(transcriber: Transcriber, address: tuple[str, int], stop: threading.Event | None = None) -> None`. `format_devices(devices: Sequence[DeviceInfo], keyboards: Sequence[str]) -> str`. `stop_requested() -> bool`. `run_serve(config: Config, listen: str | None, remote: str | None) -> int`. `run_devices() -> int`.

- [ ] **Step 1: Write the failing test**

`tests/test_runtime.py`:

```python
from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Iterator

import numpy as np
import pytest

from voxkey import paths, runtime
from voxkey.audio.devices import DeviceInfo
from voxkey.config import Config
from voxkey.net.tcp import RemoteRequest, decode_response, encode_request
from voxkey.transcribe.base import FakeTranscriber
from voxkey.transcribe.remote import RemoteTranscriber


def test_a_configured_remote_selects_the_remote_transcriber() -> None:
    transcriber = runtime.build_transcriber(Config(remote="10.0.0.2:5555"))
    assert isinstance(transcriber, RemoteTranscriber)


def test_no_remote_loads_a_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[str] = []

    def fake_load_model(choice: object) -> object:
        loaded.append(str(choice))
        return object()

    monkeypatch.setattr(runtime, "load_model", fake_load_model)
    monkeypatch.setattr(runtime, "detect_cuda", lambda: False)
    runtime.build_transcriber(Config())
    assert loaded and "small" in loaded[0]


def test_a_configured_model_name_overrides_the_automatic_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(runtime, "load_model", lambda choice: loaded.append(choice.name))
    monkeypatch.setattr(runtime, "detect_cuda", lambda: False)
    runtime.build_transcriber(Config(model="large-v3"))
    assert loaded == ["large-v3"]


def test_stop_requested_consumes_the_flag(xdg: Path) -> None:
    assert runtime.stop_requested() is False
    paths.stop_file().parent.mkdir(parents=True, exist_ok=True)
    paths.stop_file().write_text("stop")
    assert runtime.stop_requested() is True
    assert runtime.stop_requested() is False


def test_device_listing_names_both_kinds() -> None:
    listing = runtime.format_devices(
        [DeviceInfo(index=1, name="pipewire", max_input_channels=2)],
        ["/dev/input/event3"],
    )
    assert "pipewire" in listing
    assert "/dev/input/event3" in listing


@pytest.fixture
def tcp_server() -> Iterator[tuple[tuple[str, int], FakeTranscriber]]:
    transcriber = FakeTranscriber(["server heard you"])
    # Take a free port from the kernel, then release it so run_tcp_server can
    # bind it itself. getsockname must be read before the socket is closed.
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_socket.bind(("127.0.0.1", 0))
    address = probe_socket.getsockname()
    probe_socket.close()
    stop = threading.Event()
    thread = threading.Thread(
        target=runtime.run_tcp_server, args=(transcriber, address, stop), daemon=True
    )
    thread.start()
    for _ in range(200):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.connect(address)
        except OSError:
            threading.Event().wait(0.01)
            continue
        else:
            probe.close()
            break
    yield address, transcriber
    stop.set()
    thread.join(timeout=5)


def test_the_tcp_server_transcribes_what_it_is_sent(
    tcp_server: tuple[tuple[str, int], FakeTranscriber],
) -> None:
    address, transcriber = tcp_server
    frame = encode_request(
        RemoteRequest("fr", "Terms: a.", np.ones(32, dtype=np.float32))
    )
    with socket.create_connection(address, 5) as connection:
        connection.sendall(frame)
        connection.shutdown(socket.SHUT_WR)
        payload = b""
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            payload += chunk
    assert decode_response(payload) == "server heard you"
    assert transcriber.calls == [("fr", "Terms: a.", 32)]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_runtime.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.runtime'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/runtime.py`:

```python
"""Wiring the tested pieces to real devices.

Everything here is assembly: which transcriber to build, which microphone to
open, how to run the headless server. The decisions themselves live in the
modules this one imports, which is why this file stays short.
"""

from __future__ import annotations

import dataclasses
import logging
import socket
import threading
import time
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from voxkey import paths
from voxkey.audio.calibration import (
    CALIBRATION_SECS,
    DEFAULT_RETRIES,
    RETRY_DELAY_SECS,
    retry_reason,
    rms,
    threshold_from_ambient,
)
from voxkey.audio.capture import SilenceDetector, record_utterance
from voxkey.audio.devices import (
    DeviceInfo,
    StreamAudioSource,
    choose_input_device,
    list_input_devices,
)
from voxkey.config import Config
from voxkey.ipc.server import Daemon
from voxkey.net.tcp import RemoteError, decode_request, encode_error, encode_response
from voxkey.ptt.keyboard import NoKeyboardError, find_keyboards
from voxkey.transcribe.base import Transcriber
from voxkey.transcribe.local import LocalTranscriber, detect_cuda, load_model, pick_defaults
from voxkey.transcribe.remote import RemoteTranscriber, parse_address

logger = logging.getLogger(__name__)

BACKLOG = 1
ACCEPT_TIMEOUT_SECS = 0.2


def build_transcriber(config: Config) -> Transcriber:
    """A remote transcriber when one is configured, a resident model otherwise."""
    if config.remote:
        logger.info("transcription delegated to %s", config.remote)
        return RemoteTranscriber(parse_address(config.remote))
    choice = pick_defaults(has_cuda=detect_cuda())
    if config.model:
        choice = dataclasses.replace(choice, name=config.model)
    logger.info(
        "loading %s on %s (%s)", choice.name, choice.device, choice.compute_type
    )
    return LocalTranscriber(load_model(choice))


def stop_requested() -> bool:
    """Whether a client asked for the recording to end, consuming the request."""
    flag = paths.stop_file()
    if not flag.exists():
        return False
    flag.unlink(missing_ok=True)
    return True


def calibrate(device: int | None, retries: int = DEFAULT_RETRIES) -> float:
    """Sample the room and derive a speech threshold, retrying on a bad reading."""
    for attempt in range(retries):
        source = StreamAudioSource(device)
        levels: list[float] = []
        blocks = source.blocks()
        wanted = max(1, int(CALIBRATION_SECS / 0.1))
        for _ in range(wanted):
            levels.append(rms(next(blocks)))
        blocks.close()
        ambient = sum(levels) / len(levels) if levels else 0.0
        reason = retry_reason(ambient)
        if reason is None or attempt == retries - 1:
            threshold = threshold_from_ambient(ambient)
            logger.info("ambient=%.4f threshold=%.4f", ambient, threshold)
            return threshold
        logger.warning(
            "microphone reported %s (rms=%.4f), retrying in %.0fs",
            reason,
            ambient,
            RETRY_DELAY_SECS,
        )
        threading.Event().wait(RETRY_DELAY_SECS)
    return threshold_from_ambient(0.0)


class StreamRecorder:
    """Recorder backed by a real microphone."""

    def __init__(self, device: int | None, config: Config) -> None:
        self._device = device
        self._config = config
        self._threshold = calibrate(device)

    def record(
        self, wait_secs: float, silence_secs: float
    ) -> npt.NDArray[np.float32] | None:
        detector = SilenceDetector(
            threshold=self._threshold, silence_secs=silence_secs, wait_secs=wait_secs
        )
        source = StreamAudioSource(self._device)
        origin = time.monotonic()
        return record_utterance(
            source,
            detector,
            clock=lambda: time.monotonic() - origin,
            stop_flag=stop_requested,
        )


def run_tcp_server(
    transcriber: Transcriber,
    address: tuple[str, int],
    stop: threading.Event | None = None,
) -> None:
    """Headless transcription server. No microphone, no keyboard."""
    stopping = stop if stop is not None else threading.Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen(BACKLOG)
    listener.settimeout(ACCEPT_TIMEOUT_SECS)
    logger.info("listening for audio on %s:%s", *address)
    try:
        while not stopping.is_set():
            try:
                connection, peer = listener.accept()
            except TimeoutError:
                continue
            with connection:
                try:
                    with connection.makefile("rb") as stream:
                        request = decode_request(stream)
                    text = transcriber.transcribe(
                        request.audio, request.language, request.initial_prompt or None
                    )
                    connection.sendall(encode_response(text))
                except (RemoteError, OSError, ValueError) as error:
                    logger.warning("request from %s failed: %s", peer, error)
                    connection.sendall(encode_error(str(error)))
    finally:
        listener.close()


def format_devices(devices: Sequence[DeviceInfo], keyboards: Sequence[str]) -> str:
    lines = ["Audio input devices:"]
    for device in devices:
        if device.max_input_channels > 0:
            lines.append(f"  {device.index}: {device.name}")
    lines.append("Keyboards:")
    lines.extend(f"  {path}" for path in keyboards)
    return "\n".join(lines)


def run_devices() -> int:
    try:
        keyboards = find_keyboards()
    except NoKeyboardError as error:
        keyboards = []
        logger.warning("%s", error)
    print(format_devices(list_input_devices(), keyboards))
    return 0


def run_serve(config: Config, listen: str | None, remote: str | None) -> int:
    """Run the daemon, or the headless server when --listen is given."""
    effective = config if remote is None else dataclasses.replace(config, remote=remote)
    transcriber = build_transcriber(effective)

    if listen is not None:
        run_tcp_server(transcriber, parse_address(listen))
        return 0

    device = choose_input_device(list_input_devices())
    if device is None:
        logger.error("no input device found")
        return 1
    daemon = Daemon(
        transcriber=transcriber,
        recorder=StreamRecorder(device, effective),
        socket_path=paths.socket_file(),
        config=effective,
    )
    daemon.serve_forever()
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_runtime.py -v && ruff check . && mypy`
Expected: 6 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/runtime.py tests/test_runtime.py
git commit -m "Wire the daemon and the headless server to real devices

Assembly only: which transcriber to build, which microphone to open, how to
run the TCP server. The headless server is covered by an integration test over
a loopback socket with a fake model."
```

---

### Task 18: `ptt/runner.py`, the push-to-talk loop

**Files:**
- Create: `src/voxkey/ptt/runner.py`
- Create: `tests/test_ptt_runner.py`

**Interfaces:**
- Consumes: `voxkey.ptt.machine`, `voxkey.ipc.client`, `voxkey.output`.
- Produces: `Session` Protocol with `start() -> None`, `finish() -> str`, `abort() -> None`. `FakeSession` for tests. `run_push_to_talk(events: Iterable[KeyEvent], session: Session, deliver: Callable[[str], None], min_hold_secs: float = MIN_HOLD_SECS) -> None`. `DaemonSession(socket_path, language, initial_prompt)`. `run_listen(config: Config) -> int`.

- [ ] **Step 1: Write the failing test**

`tests/test_ptt_runner.py`:

```python
from __future__ import annotations

from voxkey.ptt.machine import KeyEvent
from voxkey.ptt.runner import FakeSession, run_push_to_talk


def test_a_genuine_hold_delivers_the_text() -> None:
    session = FakeSession(["hello there"])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(False, 2.0)], session, delivered.append
    )
    assert delivered == ["hello there"]
    assert session.log == ["start", "finish"]


def test_a_phantom_press_aborts_and_delivers_nothing() -> None:
    session = FakeSession(["subtitle boilerplate"])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(False, 0.3)], session, delivered.append
    )
    assert delivered == []
    assert session.log == ["start", "abort"]


def test_empty_text_is_not_delivered() -> None:
    session = FakeSession([""])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(False, 2.0)], session, delivered.append
    )
    assert delivered == []


def test_two_holds_deliver_twice() -> None:
    session = FakeSession(["first", "second"])
    delivered: list[str] = []
    run_push_to_talk(
        [
            KeyEvent(True, 0.0),
            KeyEvent(False, 2.0),
            KeyEvent(True, 5.0),
            KeyEvent(False, 8.0),
        ],
        session,
        delivered.append,
    )
    assert delivered == ["first", "second"]


def test_a_repeat_event_does_not_start_a_second_session() -> None:
    session = FakeSession(["once"])
    delivered: list[str] = []
    run_push_to_talk(
        [KeyEvent(True, 0.0), KeyEvent(True, 0.5), KeyEvent(False, 2.0)],
        session,
        delivered.append,
    )
    assert session.log == ["start", "finish"]
    assert delivered == ["once"]


def test_a_failing_session_does_not_stop_the_loop() -> None:
    session = FakeSession(["ok"], fail_first=True)
    delivered: list[str] = []
    run_push_to_talk(
        [
            KeyEvent(True, 0.0),
            KeyEvent(False, 2.0),
            KeyEvent(True, 5.0),
            KeyEvent(False, 8.0),
        ],
        session,
        delivered.append,
    )
    assert delivered == ["ok"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ptt_runner.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.ptt.runner'`.

- [ ] **Step 3: Write the implementation**

`src/voxkey/ptt/runner.py`:

```python
"""The push-to-talk loop.

The loop is a pure consumer of key events and a Session, so the phantom press
behaviour is tested without a keyboard, a daemon or a clipboard. Only
``DaemonSession`` and ``run_listen`` touch the outside world.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Protocol

from voxkey import hints, paths, state
from voxkey.config import Config
from voxkey.ipc.client import dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.output import clipboard, sound
from voxkey.ptt.keyboard import key_events, resolve_key
from voxkey.ptt.machine import MIN_HOLD_SECS, HoldDecision, HoldMachine, KeyEvent

logger = logging.getLogger(__name__)


class Session(Protocol):
    def start(self) -> None:
        """Ask the daemon to begin recording."""

    def finish(self) -> str:
        """End the recording and return the transcribed text."""

    def abort(self) -> None:
        """End the recording and throw the result away."""


class FakeSession:
    """A Session for tests, recording the calls it received."""

    def __init__(self, texts: Sequence[str], fail_first: bool = False) -> None:
        self._texts = list(texts)
        self._index = 0
        self._fail_first = fail_first
        self.log: list[str] = []

    def start(self) -> None:
        self.log.append("start")

    def finish(self) -> str:
        self.log.append("finish")
        if self._fail_first:
            self._fail_first = False
            raise RuntimeError("daemon went away")
        text = self._texts[min(self._index, len(self._texts) - 1)]
        self._index += 1
        return text

    def abort(self) -> None:
        self.log.append("abort")


def run_push_to_talk(
    events: Iterable[KeyEvent],
    session: Session,
    deliver: Callable[[str], None],
    min_hold_secs: float = MIN_HOLD_SECS,
) -> None:
    """Turn key holds into delivered text. Never raises on a single failure."""
    machine = HoldMachine(min_hold_secs=min_hold_secs)
    for event in events:
        decision = machine.feed(event)
        try:
            match decision:
                case HoldDecision.START:
                    session.start()
                case HoldDecision.ACCEPT:
                    text = session.finish()
                    if text:
                        deliver(text)
                    else:
                        logger.info("nothing was said")
                case HoldDecision.DISCARD:
                    logger.info("press too short, discarded as a phantom")
                    session.abort()
                case HoldDecision.IGNORE:
                    pass
        except Exception:  # noqa: BLE001  # one bad dictation must not end the loop
            logger.exception("dictation failed, continuing")


class DaemonSession:
    """Session backed by the daemon over its Unix socket."""

    def __init__(self, socket_path: Path, language: str) -> None:
        self._socket_path = socket_path
        self._language = language
        self._thread: threading.Thread | None = None
        self._text = ""
        self._error: BaseException | None = None

    def _dictate(self) -> None:
        try:
            self._text = dictate_once(
                self._socket_path,
                DictationRequest(
                    language=self._language, initial_prompt=hints.load_hints()
                ),
            )
        except BaseException as error:  # noqa: BLE001  # re-raised in finish
            self._error = error

    def start(self) -> None:
        self._text = ""
        self._error = None
        self._thread = threading.Thread(target=self._dictate, daemon=True)
        self._thread.start()

    def _join(self) -> None:
        # Releasing the key raises the stop flag; the daemon then stops
        # recording and answers, which lets the worker thread finish.
        state.write_atomic(paths.stop_file(), "stop")
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def finish(self) -> str:
        self._join()
        if self._error is not None:
            raise self._error
        return self._text

    def abort(self) -> None:
        self._join()


def run_listen(config: Config) -> int:
    """Read the push-to-talk key and deliver dictations to the clipboard."""
    from voxkey.ptt.keyboard import find_keyboards

    key_code = resolve_key(config.key)
    device_path = find_keyboards()[0]
    language = state.get_language(config)
    session = DaemonSession(paths.socket_file(), language)

    def deliver(text: str) -> None:
        clipboard.copy(text)
        sound.play(sound.SOUND_COMPLETE)

    logger.info("holding %s dictates, reading %s", config.key, device_path)
    run_push_to_talk(key_events(device_path, key_code), session, deliver)
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_ptt_runner.py -v && ruff check . && mypy`
Expected: 6 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/voxkey/ptt/runner.py tests/test_ptt_runner.py
git commit -m "Drive dictations from key holds, with a testable loop

The loop consumes key events and a Session, so the phantom press behaviour is
covered without a keyboard, a daemon or a clipboard. A failed dictation logs
and the loop continues rather than leaving the user with a dead key."
```

---

### Task 19: `ipc/client.py` and `cli.py`

**Files:**
- Create: `src/voxkey/ipc/client.py`
- Create: `src/voxkey/cli.py`
- Create: `src/voxkey/__main__.py`
- Create: `tests/test_ipc_client.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `client.dictate_once(socket_path, request, on_status=None) -> str`, `client.DaemonUnavailableError(RuntimeError)`. `cli.build_parser() -> argparse.ArgumentParser`, `cli.main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_ipc_client.py`:

```python
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest

from voxkey.config import Config
from voxkey.ipc.client import DaemonUnavailableError, dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.ipc.server import Daemon, FakeRecorder
from voxkey.transcribe.base import FakeTranscriber


def test_client_and_daemon_agree(xdg: Path, tmp_path: Path) -> None:
    socket_path = tmp_path / "voxkey.sock"
    daemon = Daemon(
        transcriber=FakeTranscriber(["round trip"]),
        recorder=FakeRecorder([np.ones(160, dtype=np.float32)]),
        socket_path=socket_path,
        config=Config(),
    )
    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if socket_path.exists():
                break
            threading.Event().wait(0.01)
        seen: list[str] = []
        text = dictate_once(
            socket_path, DictationRequest(language="en"), on_status=seen.append
        )
        assert text == "round trip"
        assert seen == ["recording", "transcribing"]
    finally:
        daemon.stop()
        thread.join(timeout=5)


def test_absent_daemon_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(DaemonUnavailableError, match="not running"):
        dictate_once(tmp_path / "absent.sock", DictationRequest())
```

`tests/test_cli.py`:

```python
from __future__ import annotations

import pytest

from voxkey.cli import build_parser, main


def test_every_documented_subcommand_parses() -> None:
    parser = build_parser()
    for command in ("serve", "listen", "once", "lang", "stop", "devices"):
        assert parser.parse_args([command]).command == command


def test_serve_accepts_listen_and_remote() -> None:
    parser = build_parser()
    assert parser.parse_args(["serve", "--listen", "0.0.0.0:5555"]).listen == (
        "0.0.0.0:5555"
    )
    assert parser.parse_args(["serve", "--remote", "10.0.0.2:5555"]).remote == (
        "10.0.0.2:5555"
    )


def test_listen_and_remote_are_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["serve", "--listen", "0.0.0.0:1", "--remote", "h:2"])


def test_lang_takes_an_optional_code() -> None:
    parser = build_parser()
    assert parser.parse_args(["lang"]).code is None
    assert parser.parse_args(["lang", "fr"]).code == "fr"


def test_options_belonging_to_serve_are_rejected_elsewhere() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["once", "--listen", "0.0.0.0:5555"])


def test_no_command_prints_help_and_fails() -> None:
    assert main([]) == 2


def test_version_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "voxkey" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ipc_client.py tests/test_cli.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voxkey.ipc.client'`.

- [ ] **Step 3: Write the client**

`src/voxkey/ipc/client.py`:

```python
"""Talking to the daemon."""

from __future__ import annotations

import socket
from collections.abc import Callable
from pathlib import Path

from voxkey.ipc.protocol import (
    DictationRequest,
    ErrorMessage,
    ResultMessage,
    StatusMessage,
    decode_reply,
    encode_request,
)

RECEIVE_CHUNK = 4096


class DaemonUnavailableError(RuntimeError):
    """The daemon is not listening on the socket."""


def dictate_once(
    socket_path: Path,
    request: DictationRequest,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """Ask the daemon for one dictation and return the text."""
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.connect(str(socket_path))
    except (FileNotFoundError, ConnectionRefusedError) as error:
        raise DaemonUnavailableError(
            f"the voxkey daemon is not running on {socket_path}. Start it with "
            f"'voxkey serve', or 'systemctl --user start voxkey.service'."
        ) from error

    with connection:
        connection.sendall(encode_request(request))
        connection.shutdown(socket.SHUT_WR)
        buffer = b""
        while True:
            chunk = connection.recv(RECEIVE_CHUNK)
            if not chunk:
                break
            buffer += chunk

    text = ""
    for line in buffer.splitlines():
        if not line.strip():
            continue
        reply = decode_reply(line)
        match reply:
            case StatusMessage(status) if on_status is not None:
                on_status(status)
            case ResultMessage(result):
                text = result
            case ErrorMessage(message):
                raise RuntimeError(message)
            case _:
                pass
    return text
```

- [ ] **Step 4: Write the CLI**

`src/voxkey/cli.py`:

```python
"""The voxkey command line.

Subcommands rather than flags, so each mode owns its options and its help. This
module only parses and dispatches; it holds no behaviour of its own.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from voxkey import __version__, hints, paths, runtime, state
from voxkey.config import ConfigError, load
from voxkey.i18n import _, setup
from voxkey.ipc.client import DaemonUnavailableError, dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.languages import language_name
from voxkey.ptt.runner import run_listen

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voxkey",
        description="Push-to-talk dictation for Linux, transcribed locally.",
    )
    parser.add_argument("--version", action="version", version=f"voxkey {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log at debug level"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    serve = subparsers.add_parser("serve", help="run the daemon, keeping the model resident")
    target = serve.add_mutually_exclusive_group()
    target.add_argument(
        "--listen", metavar="HOST:PORT", help="run as a headless transcription server"
    )
    target.add_argument(
        "--remote", metavar="HOST:PORT", help="record here, transcribe on that server"
    )

    subparsers.add_parser("listen", help="run the push-to-talk client")
    subparsers.add_parser("once", help="one dictation, text on standard output")

    lang = subparsers.add_parser("lang", help="cycle or set the transcription language")
    lang.add_argument("code", nargs="?", help="language code, or omit to cycle")

    subparsers.add_parser("stop", help="stop the daemon")
    subparsers.add_parser("devices", help="list audio devices and keyboards")
    return parser


def _command_once(config_language: str) -> int:
    request = DictationRequest(
        language=config_language, initial_prompt=hints.load_hints()
    )
    try:
        text = dictate_once(paths.socket_file(), request)
    except DaemonUnavailableError as error:
        print(str(error), file=sys.stderr)
        return 1
    if not text:
        print(_("No speech detected"), file=sys.stderr)
        return 1
    print(text)
    return 0


def _command_lang(
    code: str | None, config_language: str, languages: Sequence[str]
) -> int:
    target = (
        code if code is not None else state.next_language(config_language, languages)
    )
    state.set_language(target)
    print(
        _("Language: {name} ({code})").format(name=language_name(target), code=target)
    )
    return 0


def _command_stop() -> int:
    socket_path = paths.socket_file()
    if not socket_path.exists():
        print("the voxkey daemon is not running", file=sys.stderr)
        return 1
    state.write_atomic(paths.stop_file(), "stop")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    try:
        config = load()
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    setup()
    language = state.get_language(config)

    match args.command:
        case "once":
            return _command_once(language)
        case "lang":
            return _command_lang(args.code, language, config.languages)
        case "stop":
            return _command_stop()
        case "serve":
            return runtime.run_serve(config, listen=args.listen, remote=args.remote)
        case "listen":
            return run_listen(config)
        case "devices":
            return runtime.run_devices()
        case _:
            parser.print_help(sys.stderr)
            return 2
```

`src/voxkey/__main__.py`:

```python
from __future__ import annotations

from voxkey.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest -v && ruff check . && mypy`
Expected: the whole suite passes, ruff clean, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/voxkey/ipc/client.py src/voxkey/cli.py src/voxkey/__main__.py tests/test_ipc_client.py tests/test_cli.py
git commit -m "Add the client and the subcommand parser

Each mode now owns its options, so --listen and --remote can only appear where
they mean something and the parser rejects them elsewhere."
```

---

## Definition of done for this plan

- [ ] `pytest` passes with no skipped tests on Python 3.12 and 3.13.
- [ ] `ruff check .` and `mypy` are clean.
- [ ] `voxkey once` produces text through a daemon started by `voxkey serve` on the developer's machine, verified by hand.
- [ ] No test touches a microphone, a keyboard, a GPU, an X server or an outside network host.
- [ ] Every trap in section 14 of the spec has a named regression test.

## What plan 2 and plan 3 pick up

Plan 1 delivers every subcommand in working order. It deliberately stops short of three things:

- The tray and the control window are plan 2. Both consume `voxkey.state`, `voxkey.config` and `voxkey.ipc.client` exactly as this plan leaves them, so plan 2 adds no core changes.
- The systemd units, the desktop entries, the `sg input` wrapper, the installer, the Claude Code commands and the Jetson wheel build are plan 3.
- Migration from `~/.config/dictate`, the catalogue build hook that compiles `.mo` into the wheel, the README, the CHANGELOG, the LICENSE and publication are plan 3.

Until plan 3 lands, the package runs from a checkout with `pip install -e .` and `python tools/compile_catalogs.py`, and the daemon is started by hand rather than by systemd.
