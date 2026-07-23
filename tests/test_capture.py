from __future__ import annotations

import numpy as np

from voxkey.audio.capture import (
    SAMPLE_RATE,
    ContinuousCapture,
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


def test_continuous_noise_hits_the_hard_ceiling() -> None:
    # Noise forever above the threshold means the silence branch never fires;
    # without the ceiling the recording would grow without bound.
    detector = SilenceDetector(
        threshold=0.1, silence_secs=3.0, wait_secs=10.0, max_secs=60.0
    )
    assert detector.feed(0.5, now=59.9) is True
    assert detector.feed(0.5, now=60.0) is False
    assert detector.finished is True
    # What was said before the ceiling is kept, not discarded.
    assert detector.speech_detected is True


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


def test_prebuffer_snapshot_returns_the_last_window() -> None:
    buffer = PreBuffer(max_secs=1.0, sample_rate=10)
    for value in range(15):
        buffer.append(np.full(1, float(value), dtype=np.float32))
    snapshot = buffer.snapshot()
    assert len(snapshot) == 10
    assert snapshot[0] == 5.0
    assert snapshot[-1] == 14.0


def test_prebuffer_snapshot_does_not_clear_the_buffer() -> None:
    buffer = PreBuffer(max_secs=1.0, sample_rate=10)
    buffer.append(np.full(3, 1.0, dtype=np.float32))
    first = buffer.snapshot()
    second = buffer.snapshot()
    assert len(first) == 3
    assert len(second) == 3
    # drain() still sees the same, unconsumed contents.
    assert len(buffer.drain()) == 3


def test_continuous_capture_pump_rolls_the_prebuffer_before_any_arm() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    for value in range(15):
        capture.pump(np.full(1, float(value), dtype=np.float32), now=0.0)
    assert capture.armed is False
    assert capture.finished is False
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector)
    capture.mark_finished()
    result = capture.result()
    assert result is not None
    # Only the last 10 samples (the buffer's capacity) survive the overfill.
    assert list(result) == [float(v) for v in range(5, 15)]


def test_continuous_capture_prepends_prebuffer_snapshot_to_the_recording() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    for value in range(10):
        capture.pump(np.array([float(value)], dtype=np.float32), now=0.0)
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector)
    capture.pump(np.array([99.0], dtype=np.float32), now=0.0)
    capture.mark_finished()
    result = capture.result()
    assert result is not None
    assert list(result) == [float(v) for v in range(10)] + [99.0]


def test_continuous_capture_stops_recording_on_silence_after_speech() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector)
    capture.pump(np.full(1, 0.5, dtype=np.float32), now=0.0)
    capture.pump(np.zeros(1, dtype=np.float32), now=1.0)
    assert capture.finished is False
    capture.pump(np.zeros(1, dtype=np.float32), now=2.9)
    assert capture.finished is False
    capture.pump(np.zeros(1, dtype=np.float32), now=3.1)
    assert capture.finished is True
    result = capture.result()
    assert result is not None
    assert len(result) == 4  # empty pre-buffer + 4 recorded blocks


def test_continuous_capture_no_speech_yields_none() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=5.0)
    capture.arm(detector)
    for now in (0.0, 1.0, 2.0, 3.0, 5.1):
        capture.pump(np.zeros(1, dtype=np.float32), now=now)
    assert capture.finished is True
    assert capture.result() is None


def test_continuous_capture_manual_stop_over_silence_still_counts() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector)
    capture.pump(np.zeros(1, dtype=np.float32), now=0.0)
    capture.mark_finished()
    assert capture.finished is True
    assert detector.speech_detected is True
    result = capture.result()
    assert result is not None
    assert len(result) == 1

    # A pump call after mark_finished must not extend the recording further.
    capture.pump(np.zeros(1, dtype=np.float32), now=1.0)
    result_after = capture.result()
    assert result_after is not None
    assert len(result_after) == 1


def test_continuous_capture_disarm_keeps_the_prebuffer_rolling() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    detector_one = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector_one)
    capture.pump(np.full(1, 0.5, dtype=np.float32), now=0.0)
    capture.mark_finished()
    capture.result()
    capture.disarm()
    assert capture.armed is False

    for value in range(100, 110):
        capture.pump(np.array([float(value)], dtype=np.float32), now=0.0)

    detector_two = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector_two)
    capture.mark_finished()
    result = capture.result()
    assert result is not None
    assert list(result) == [float(v) for v in range(100, 110)]


def test_continuous_capture_disarm_drops_the_detector_so_result_is_none() -> None:
    capture = ContinuousCapture(pre_buffer_secs=1.0, sample_rate=10)
    detector = SilenceDetector(threshold=0.1, silence_secs=3.0, wait_secs=10.0)
    capture.arm(detector)
    capture.pump(np.full(1, 0.5, dtype=np.float32), now=0.0)
    capture.mark_finished()
    capture.disarm()
    assert capture.result() is None
