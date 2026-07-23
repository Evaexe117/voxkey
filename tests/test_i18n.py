from __future__ import annotations

import sys
from pathlib import Path

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


def test_shipped_french_catalogue_covers_every_live_string() -> None:
    # Guards the packaging pipeline and catalogue drift: the shipped .po must
    # carry an entry for every string the code actually passes through _(), so a
    # real install shows French, not a silent English fallback. Checking
    # membership (not translated != source) is deliberate: some names, like
    # "Hindi", are legitimately identical in French.
    from tools.compile_catalogs import parse_po
    from voxkey.languages import NAMES

    po = Path("src/voxkey/locales/fr/LC_MESSAGES/voxkey.po").read_text()
    catalogue = parse_po(po)
    live_strings = [
        "No speech detected",
        "Language: {name} ({code})",
        "Warning: {code} is not a known language code",
        *NAMES.values(),
    ]
    missing = [s for s in live_strings if s not in catalogue]
    assert missing == [], f"strings with no French catalogue entry: {missing}"
