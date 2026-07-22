"""Recording, and deciding when to stop.

dictate made this decision inside a PortAudio callback closing over four
mutable variables, which cannot be tested. Here the decision is a state machine
fed one level at a time, and the device is a Protocol.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt

from voxkey.audio.calibration import rms

SAMPLE_RATE = 16000
BLOCK_SECS = 0.1


class AudioSource(Protocol):
    def blocks(self) -> Iterator[npt.NDArray[np.float32]]:
        """Yield successive blocks of mono float32 samples."""


class SyntheticAudioSource:
    """An AudioSource for tests, with a clock that advances one block at a time."""

    def __init__(
        self, blocks: Sequence[npt.NDArray[np.float32]], block_secs: float = BLOCK_SECS
    ) -> None:
        self._blocks = list(blocks)
        self._block_secs = block_secs
        self._elapsed = 0.0

    def blocks(self) -> Iterator[npt.NDArray[np.float32]]:
        for block in self._blocks:
            yield block
            self._elapsed += self._block_secs

    def clock(self) -> float:
        return self._elapsed


class SilenceDetector:
    """Decide, level by level, whether recording should continue."""

    def __init__(self, threshold: float, silence_secs: float, wait_secs: float) -> None:
        self._threshold = threshold
        self._silence_secs = silence_secs
        self._wait_secs = wait_secs
        self._last_speech = 0.0
        self.speech_detected = False
        self.finished = False

    def feed(self, level: float, now: float) -> bool:
        """Return True to keep recording, False to stop.

        ``now`` is measured from the start of the recording (clock() reads
        0.0 when recording begins), so waiting for speech is judged against
        that fixed origin rather than against whenever ``feed`` first happens
        to be called.
        """
        if level > self._threshold:
            self.speech_detected = True
            self._last_speech = now
            return True
        if self.speech_detected:
            if now - self._last_speech >= self._silence_secs:
                self.finished = True
                return False
            return True
        if now >= self._wait_secs:
            self.finished = True
            return False
        return True


class PreBuffer:
    """A rolling window of the most recent audio.

    This is what removes the delay at the start of a dictation: the words
    spoken before recording actually begins are already in here.
    """

    def __init__(self, max_secs: float, sample_rate: int = SAMPLE_RATE) -> None:
        self._samples: deque[float] = deque(maxlen=int(max_secs * sample_rate))

    def append(self, block: npt.NDArray[np.float32]) -> None:
        self._samples.extend(block.tolist())

    def drain(self) -> npt.NDArray[np.float32]:
        drained: npt.NDArray[np.float32] = np.array(self._samples, dtype=np.float32)
        self._samples.clear()
        return drained


def record_utterance(
    source: AudioSource,
    detector: SilenceDetector,
    clock: Callable[[], float],
    stop_flag: Callable[[], bool] | None = None,
) -> npt.NDArray[np.float32] | None:
    """Record until the detector says stop, or the stop flag is raised.

    Returns None when no speech was ever heard, which the caller reports rather
    than sending an empty buffer to the model.

    ``clock`` must read 0.0 at the start of the recording and increase with
    elapsed time: SilenceDetector measures its wait window against that origin.
    A clock that does not start at 0, such as a bare time.monotonic(), makes the
    give-up branch fire immediately. Callers wiring a real device pass a clock
    zeroed at the first block; see StreamRecorder in runtime.
    """
    collected: list[npt.NDArray[np.float32]] = []
    for block in source.blocks():
        collected.append(block)
        if stop_flag is not None and stop_flag():
            # A manual stop is a valid recording, whatever the levels were.
            detector.speech_detected = True
            break
        if not detector.feed(rms(block), clock()):
            break
    if not collected or not detector.speech_detected:
        return None
    return np.concatenate(collected).astype(np.float32)
