"""Vocabulary hints handed to Whisper as its initial prompt.

Proper nouns, acronyms and technical terms transcribe badly without context.
Hints are merged per request, global first then project, so switching project
directories needs no restart.

``hotwords`` degrades transcription when many terms are supplied, which is why
this becomes ``initial_prompt`` instead.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from voxkey import paths

logger = logging.getLogger(__name__)

#: Hints are short vocabulary lists; anything bigger is a mistake or an attack
#: and would be shipped verbatim to a remote transcription server.
MAX_HINTS_FILE_BYTES = 64 * 1024


def read_hints_file(path: Path) -> list[str]:
    words: list[str] = []
    # errors="replace" tolerates a file that is not UTF-8; the OSError guard
    # tolerates one that cannot be read at all (permissions). A single bad hints
    # file must never break every dictation, so it is skipped, not raised.
    try:
        if path.stat().st_size > MAX_HINTS_FILE_BYTES:
            logger.warning("skipping oversized hints file %s", path)
            return words
        text = path.read_text(errors="replace")
    except OSError:
        logger.warning("skipping unreadable hints file %s", path)
        return words
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        words.append(line)
    return words


def read_hints_dir(directory: Path) -> list[str]:
    # Symlinks are refused outright: a hostile project directory containing
    # `.voxkey-hints.d/terms -> /proc/self/environ` would otherwise smuggle
    # arbitrary local files into the prompt sent to a remote transcription
    # server. Same reasoning for a symlinked hints directory itself.
    if directory.is_symlink() or not directory.is_dir():
        return []
    words: list[str] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError:
        logger.warning("skipping unreadable hints directory %s", directory)
        return words
    for entry in entries:
        if entry.is_symlink():
            logger.warning("skipping symlinked hints entry %s", entry)
            continue
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
