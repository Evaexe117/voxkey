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


def setup(
    languages: Sequence[str] | None = None, localedir: Path | None = None
) -> None:
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
