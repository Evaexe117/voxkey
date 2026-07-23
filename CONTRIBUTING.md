# Contributing

## Running the checks

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,gui]"
pytest
ruff check .
mypy
```

CI runs ruff, mypy (strict) and the full test suite on Python 3.12 and 3.13.
Every check must stay green in every commit.

The tests run without a microphone, a keyboard, or a display; nothing in the
suite records audio or loads a Whisper model.

## Translations

User-visible strings are in English and wrapped in `_()` from
`voxkey.i18n`. French is a catalogue like any other; the sources live in
`src/voxkey/locales/`.

The compiled `.mo` files are build output: `hatch_build.py` compiles them
into the wheel, and for a working copy you can compile them in place with:

```bash
python tools/compile_catalogs.py
```

When you add or change a visible string, update
`src/voxkey/locales/voxkey.pot` and `src/voxkey/locales/fr/LC_MESSAGES/voxkey.po`,
then recompile. A missing entry silently falls back to English, which nobody
notices until they switch languages.

To add a language, create
`src/voxkey/locales/<code>/LC_MESSAGES/voxkey.po` from the `.pot` template,
translate every `msgstr`, and recompile. No code change is required.

## Style

- `ruff check .` and `mypy` must pass; both run in CI.
- Comments explain constraints the code cannot show, not what the next line
  does.
- Commit messages describe the change from the user's point of view, in the
  imperative or as a statement of fact. No em dash, no double hyphen outside
  command options.

## Reporting a bug

Include your distribution, desktop session (X11 or Wayland), the output of
`voxkey devices`, and the relevant journal lines:

```bash
journalctl --user -u voxkey -u voxkey-ptt --since -1h
```

Strip anything you dictated that you would rather not publish. Security
issues go through a private advisory instead, as described in
[SECURITY.md](SECURITY.md).
