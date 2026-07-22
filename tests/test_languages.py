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
