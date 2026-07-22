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
