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

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[_Segment], object]:  # noqa: ARG002
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
