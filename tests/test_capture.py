from __future__ import annotations

import numpy as np

from voxkey.audio.capture import (
    SAMPLE_RATE,
    PreBuffer,
    SilenceDetector,
    SyntheticAudioSource,
    record_utterance,
)


def test_detector_stops_after_silence_that_follows_speech() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    assert detector.feed(0.5, now=0.0) is True
    assert detector.feed(0.0, now=1.0) is True
    assert detector.feed(0.0, now=2.9) is True
    assert detector.feed(0.0, now=3.1) is False
    assert detector.speech_detected is True


def test_silence_timer_restarts_on_new_speech() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    detector.feed(0.5, now=0.0)
    detector.feed(0.0, now=2.0)
    detector.feed(0.5, now=2.5)
    assert detector.feed(0.0, now=5.0) is True


def test_detector_gives_up_when_no_speech_ever_arrives() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    assert detector.feed(0.0, now=5.0) is True
    assert detector.feed(0.0, now=10.1) is False
    assert detector.speech_detected is False


def test_a_level_exactly_at_the_threshold_is_not_speech() -> None:
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    detector.feed(0.1, now=0.0)
    assert detector.speech_detected is False


def test_prebuffer_keeps_only_the_last_second() -> None:
    buffer = PreBuffer(max_secs=1.0, sample_rate=10)
    for value in range(15):
        buffer.append(np.full(1, float(value), dtype=np.float32))
    drained = buffer.drain()
    assert len(drained) == 10
    assert drained[0] == 5.0
    assert drained[-1] == 14.0


def test_prebuffer_drain_empties_it() -> None:
    buffer = PreBuffer(max_secs=1.0, sample_rate=10)
    buffer.append(np.ones(3, dtype=np.float32))
    buffer.drain()
    assert len(buffer.drain()) == 0


def test_record_returns_the_spoken_audio() -> None:
    source = SyntheticAudioSource(
        [
            np.full(160, 0.5, dtype=np.float32),
            np.full(160, 0.5, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
            np.zeros(160, dtype=np.float32),
        ],
        block_secs=1.0,
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    audio = record_utterance(source, detector, clock=source.clock)
    assert audio is not None
    assert len(audio) == 5 * 160


def test_record_returns_none_when_nothing_was_said() -> None:
    source = SyntheticAudioSource(
        [np.zeros(160, dtype=np.float32) for _ in range(12)], block_secs=1.0
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    assert record_utterance(source, detector, clock=source.clock) is None


def test_record_stops_when_the_stop_flag_is_raised() -> None:
    source = SyntheticAudioSource(
        [np.full(160, 0.5, dtype=np.float32) for _ in range(10)], block_secs=1.0
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    calls = {"count": 0}

    def stop_flag() -> bool:
        calls["count"] += 1
        return calls["count"] >= 3

    audio = record_utterance(
        source, detector, clock=source.clock, stop_flag=stop_flag
    )
    assert audio is not None
    assert len(audio) == 3 * 160


def test_manual_stop_over_silence_still_counts_as_a_recording() -> None:
    # A manual stop is a valid recording whatever the levels were. The other
    # stop-flag test uses loud audio, so speech is already detected before the
    # stop fires; this one keeps every block silent so only the stop flag can
    # make the recording count.
    source = SyntheticAudioSource(
        [np.zeros(160, dtype=np.float32) for _ in range(10)], block_secs=1.0
    )
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    calls = {"count": 0}

    def stop_flag() -> bool:
        calls["count"] += 1
        return calls["count"] >= 2

    audio = record_utterance(
        source, detector, clock=source.clock, stop_flag=stop_flag
    )
    assert audio is not None
    assert len(audio) == 2 * 160


def test_sample_rate_is_the_one_whisper_expects() -> None:
    assert SAMPLE_RATE == 16000
