from __future__ import annotations

import numpy as np
import pytest

from voxkey.audio.calibration import (
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    retry_reason,
    rms,
    threshold_from_ambient,
)


def test_rms_of_silence_is_zero() -> None:
    assert rms(np.zeros(100, dtype=np.float32)) == 0.0


def test_rms_of_a_constant_signal_is_its_magnitude() -> None:
    assert rms(np.full(100, 0.5, dtype=np.float32)) == pytest.approx(0.5)


def test_rms_of_an_empty_buffer_is_zero() -> None:
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_threshold_is_ambient_and_a_half_plus_a_hundredth() -> None:
    assert threshold_from_ambient(0.01) == pytest.approx(0.025)


def test_threshold_is_capped() -> None:
    assert threshold_from_ambient(1.0) == MAX_THRESHOLD


def test_silence_yields_the_minimum_threshold() -> None:
    assert threshold_from_ambient(0.0) == pytest.approx(MIN_THRESHOLD)


def test_silence_asks_for_a_retry() -> None:
    assert retry_reason(0.0) == "silence"


def test_a_suspiciously_loud_reading_asks_for_a_retry() -> None:
    # PipeWire switching routes mid-calibration reads as a very loud room.
    assert retry_reason(0.5) == "noise"


def test_an_ordinary_room_does_not_ask_for_a_retry() -> None:
    assert retry_reason(0.005) is None
