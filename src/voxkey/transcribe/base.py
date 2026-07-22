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
