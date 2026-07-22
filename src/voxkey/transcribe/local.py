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
