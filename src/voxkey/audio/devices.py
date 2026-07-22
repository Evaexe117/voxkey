"""Finding a microphone.

Selection is a pure function over a list of descriptions, so the preference
rules are tested without any sound card present. Only ``list_input_devices``
and ``StreamAudioSource`` touch PortAudio.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from voxkey.audio.capture import BLOCK_SECS, SAMPLE_RATE

PREFERRED_NAME = "pipewire"


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    max_input_channels: int


def choose_input_device(devices: Sequence[DeviceInfo]) -> int | None:
    """Prefer PipeWire by name, then the first device that can record."""
    inputs = [device for device in devices if device.max_input_channels > 0]
    for device in inputs:
        if PREFERRED_NAME in device.name.casefold():
            return device.index
    return inputs[0].index if inputs else None


def list_input_devices() -> list[DeviceInfo]:
    import sounddevice

    found: list[DeviceInfo] = []
    for index, raw in enumerate(sounddevice.query_devices()):
        found.append(
            DeviceInfo(
                index=index,
                name=str(raw["name"]),
                max_input_channels=int(raw["max_input_channels"]),
            )
        )
    return found


class StreamAudioSource:
    """AudioSource backed by a real PortAudio input stream."""

    def __init__(self, device: int | None, block_secs: float = BLOCK_SECS) -> None:
        self._device = device
        self._block_frames = int(SAMPLE_RATE * block_secs)

    def blocks(self) -> Generator[npt.NDArray[np.float32], None, None]:
        import sounddevice

        with sounddevice.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self._device,
            blocksize=self._block_frames,
        ) as stream:
            while True:
                frames, _overflowed = stream.read(self._block_frames)
                block: npt.NDArray[np.float32] = np.asarray(
                    frames, dtype=np.float32
                ).flatten()
                yield block
