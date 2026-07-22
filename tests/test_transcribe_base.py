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
