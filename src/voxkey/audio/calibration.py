"""Derive the speech threshold from a sample of the room.

The decisions live here as pure functions over a number, so every branch is
covered by a test with no microphone involved. Only the sampling itself, in
``capture``, touches a device.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

CALIBRATION_SECS = 0.5
DEFAULT_RETRIES = 5
RETRY_DELAY_SECS = 2.0

#: Below this the microphone is not delivering anything usable.
SILENT_AMBIENT = 0.001
#: Above this the reading is not a room, it is a device switching mid-sample.
NOISY_AMBIENT = 0.03

MIN_THRESHOLD = 0.01
MAX_THRESHOLD = 0.05


def rms(samples: npt.NDArray[np.float32]) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def threshold_from_ambient(ambient: float) -> float:
    """Speech threshold for a measured ambient level, capped for loud rooms."""
    return min(ambient * 1.5 + MIN_THRESHOLD, MAX_THRESHOLD)


def retry_reason(ambient: float) -> str | None:
    """Why this calibration should be thrown away, or None to accept it."""
    if ambient < SILENT_AMBIENT:
        return "silence"
    if ambient > NOISY_AMBIENT:
        return "noise"
    return None
