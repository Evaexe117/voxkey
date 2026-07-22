"""Wiring the tested pieces to real devices.

Everything here is assembly: which transcriber to build, which microphone to
open, how to run the headless server. The decisions themselves live in the
modules this one imports, which is why this file stays short.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Sequence
from types import FrameType

import numpy as np
import numpy.typing as npt

from voxkey import paths, state
from voxkey.audio.calibration import (
    CALIBRATION_SECS,
    DEFAULT_RETRIES,
    RETRY_DELAY_SECS,
    retry_reason,
    rms,
    threshold_from_ambient,
)
from voxkey.audio.capture import SilenceDetector, record_utterance
from voxkey.audio.devices import (
    DeviceInfo,
    StreamAudioSource,
    choose_input_device,
    list_input_devices,
)
from voxkey.config import Config
from voxkey.ipc.server import Daemon
from voxkey.net.tcp import RemoteError, decode_request, encode_error, encode_response
from voxkey.ptt.keyboard import NoKeyboardError, find_keyboards
from voxkey.transcribe.base import Transcriber
from voxkey.transcribe.local import (
    LocalTranscriber,
    detect_cuda,
    load_model,
    pick_defaults,
)
from voxkey.transcribe.remote import RemoteTranscriber, parse_address

logger = logging.getLogger(__name__)

BACKLOG = 1
ACCEPT_TIMEOUT_SECS = 0.2


def build_transcriber(config: Config) -> Transcriber:
    """A remote transcriber when one is configured, a resident model otherwise."""
    if config.remote:
        logger.info("transcription delegated to %s", config.remote)
        return RemoteTranscriber(parse_address(config.remote))
    choice = pick_defaults(has_cuda=detect_cuda())
    if config.model:
        choice = dataclasses.replace(choice, name=config.model)
    logger.info(
        "loading %s on %s (%s)", choice.name, choice.device, choice.compute_type
    )
    return LocalTranscriber(load_model(choice))


def stop_requested() -> bool:
    """Whether a client asked for the recording to end, consuming the request."""
    flag = paths.stop_file()
    if not flag.exists():
        return False
    flag.unlink(missing_ok=True)
    return True


def calibrate(device: int | None, retries: int = DEFAULT_RETRIES) -> float:
    """Sample the room and derive a speech threshold, retrying on a bad reading."""
    for attempt in range(retries):
        source = StreamAudioSource(device)
        levels: list[float] = []
        blocks = source.blocks()
        wanted = max(1, int(CALIBRATION_SECS / 0.1))
        for _ in range(wanted):
            levels.append(rms(next(blocks)))
        blocks.close()
        ambient = sum(levels) / len(levels) if levels else 0.0
        reason = retry_reason(ambient)
        if reason is None or attempt == retries - 1:
            threshold = threshold_from_ambient(ambient)
            logger.info("ambient=%.4f threshold=%.4f", ambient, threshold)
            return threshold
        logger.warning(
            "microphone reported %s (rms=%.4f), retrying in %.0fs",
            reason,
            ambient,
            RETRY_DELAY_SECS,
        )
        threading.Event().wait(RETRY_DELAY_SECS)
    return threshold_from_ambient(0.0)


class StreamRecorder:
    """Recorder backed by a real microphone."""

    def __init__(self, device: int | None, config: Config) -> None:
        self._device = device
        self._config = config
        self._threshold = calibrate(device)

    def record(
        self, wait_secs: float, silence_secs: float
    ) -> npt.NDArray[np.float32] | None:
        detector = SilenceDetector(
            threshold=self._threshold, silence_secs=silence_secs, wait_secs=wait_secs
        )
        source = StreamAudioSource(self._device)
        origin = time.monotonic()
        return record_utterance(
            source,
            detector,
            clock=lambda: time.monotonic() - origin,
            stop_flag=stop_requested,
        )


def run_tcp_server(
    transcriber: Transcriber,
    address: tuple[str, int],
    stop: threading.Event | None = None,
) -> None:
    """Headless transcription server. No microphone, no keyboard."""
    stopping = stop if stop is not None else threading.Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen(BACKLOG)
    listener.settimeout(ACCEPT_TIMEOUT_SECS)
    logger.info("listening for audio on %s:%s", *address)
    try:
        while not stopping.is_set():
            try:
                connection, peer = listener.accept()
            except TimeoutError:
                continue
            with connection:
                try:
                    with connection.makefile("rb") as stream:
                        request = decode_request(stream)
                    text = transcriber.transcribe(
                        request.audio, request.language, request.initial_prompt or None
                    )
                    connection.sendall(encode_response(text))
                except (RemoteError, OSError, ValueError) as error:
                    logger.warning("request from %s failed: %s", peer, error)
                    connection.sendall(encode_error(str(error)))
    finally:
        listener.close()


def format_devices(devices: Sequence[DeviceInfo], keyboards: Sequence[str]) -> str:
    lines = ["Audio input devices:"]
    for device in devices:
        if device.max_input_channels > 0:
            lines.append(f"  {device.index}: {device.name}")
    lines.append("Keyboards:")
    lines.extend(f"  {path}" for path in keyboards)
    return "\n".join(lines)


def run_devices() -> int:
    try:
        keyboards = find_keyboards()
    except NoKeyboardError as error:
        keyboards = []
        logger.warning("%s", error)
    print(format_devices(list_input_devices(), keyboards))
    return 0


def run_serve(config: Config, listen: str | None, remote: str | None) -> int:
    """Run the daemon, or the headless server when --listen is given."""
    effective = config if remote is None else dataclasses.replace(config, remote=remote)
    transcriber = build_transcriber(effective)

    if listen is not None:
        run_tcp_server(transcriber, parse_address(listen))
        return 0

    device = choose_input_device(list_input_devices())
    if device is None:
        logger.error("no input device found")
        return 1
    daemon = Daemon(
        transcriber=transcriber,
        recorder=StreamRecorder(device, effective),
        socket_path=paths.socket_file(),
        config=effective,
    )

    def _handle_shutdown_signal(signum: int, frame: FrameType | None) -> None:  # noqa: ARG001
        logger.info("received signal %d, stopping", signum)
        daemon.stop()

    pid_path = paths.pid_file()
    state.write_atomic(pid_path, str(os.getpid()))
    previous_term = signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    previous_int = signal.signal(signal.SIGINT, _handle_shutdown_signal)
    try:
        daemon.serve_forever()
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
        pid_path.unlink(missing_ok=True)
    return 0
