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
from collections.abc import Callable, Generator, Iterator, Sequence
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
from voxkey.audio.capture import (
    BLOCK_SECS,
    AudioSource,
    ContinuousCapture,
    SilenceDetector,
)
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
CONNECTION_TIMEOUT_SECS = 30.0


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


POLL_SECS = BLOCK_SECS / 2
# A real microphone delivers a block every BLOCK_SECS; this much silence from
# the reader means the device has stalled, not that it is merely quiet.
READER_STALL_SECS = 5.0


class StreamRecorder:
    """Recorder backed by a persistent microphone stream with a rolling pre-buffer.

    Faithful to dictate: one audio stream stays open the whole time the daemon
    runs, a background thread feeds every block into a ContinuousCapture so the
    one-second pre-buffer keeps rolling continuously, and each dictation begins
    with whatever is already in that buffer. This is what removes the delay at
    the start of a dictation, at the cost of the microphone being open for the
    daemon's lifetime.

    The capture logic is pure and tested; this class is the thin shell that owns
    the stream, the reader thread and the lock between the reader and record().
    ``source_factory`` exists so a test can drive it with a fake persistent
    source instead of a real device.
    """

    def __init__(
        self,
        device: int | None,
        config: Config,
        source_factory: Callable[[], AudioSource] | None = None,
    ) -> None:
        self._config = config
        self._threshold = calibrate(device)
        self._make_source = source_factory or (lambda: StreamAudioSource(device))
        self._capture = ContinuousCapture(config.pre_buffer_secs)
        self._lock = threading.Lock()
        self._arm_origin = 0.0
        self._last_pump = time.monotonic()
        self._stopping = threading.Event()
        self._blocks: Iterator[npt.NDArray[np.float32]] | None = None
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        source = self._make_source()
        self._blocks = iter(source.blocks())
        try:
            for block in self._blocks:
                if self._stopping.is_set():
                    break
                try:
                    with self._lock:
                        now = time.monotonic() - self._arm_origin
                        self._last_pump = time.monotonic()
                        self._capture.pump(block, now)
                except Exception:  # noqa: BLE001  # one bad block must not retire the reader
                    logger.exception("error processing an audio block, continuing")
        except Exception:  # noqa: BLE001  # a dying stream ends the reader, not the process
            logger.exception("microphone reader stopped")

    def record(
        self, wait_secs: float, silence_secs: float
    ) -> npt.NDArray[np.float32] | None:
        detector = SilenceDetector(
            threshold=self._threshold, silence_secs=silence_secs, wait_secs=wait_secs
        )
        with self._lock:
            self._arm_origin = time.monotonic()
            self._capture.arm(detector)
        try:
            while not self._stopping.is_set():
                # If the reader thread has died (a microphone failure), no block
                # will ever advance the detector, so the wait-timeout branch can
                # never fire. Break here so a dead microphone surfaces as "no
                # speech" instead of hanging record() and, with it, the whole
                # single-threaded daemon.
                if not self._reader.is_alive():
                    logger.error("microphone reader is not running")
                    break
                # The reader can also be alive but stalled: a device that hangs
                # in read() without raising delivers no blocks, so the detector
                # never advances either. If nothing has been pumped for a while,
                # give up rather than spin forever.
                with self._lock:
                    stalled = time.monotonic() - self._last_pump > READER_STALL_SECS
                if stalled:
                    logger.error(
                        "microphone delivered no audio for %ss", READER_STALL_SECS
                    )
                    break
                if stop_requested():
                    with self._lock:
                        self._capture.mark_finished()
                    break
                with self._lock:
                    if self._capture.finished:
                        break
                time.sleep(POLL_SECS)
            with self._lock:
                return self._capture.result()
        finally:
            with self._lock:
                self._capture.disarm()

    def close(self) -> None:
        """Stop the reader thread and release the microphone stream.

        The reader checks the stop flag after each block; a real device read
        returns every block period, so it breaks promptly on its own. The
        generator is closed only once the reader has truly stopped, because a
        generator that is still executing in the reader thread cannot be closed
        from here (it raises "generator already executing").
        """
        self._stopping.set()
        self._reader.join(timeout=5)
        if not self._reader.is_alive() and isinstance(self._blocks, Generator):
            self._blocks.close()  # run StreamAudioSource's InputStream teardown


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
            # Accepted connections do not inherit the listener's accept
            # timeout. Without one, a client that connects and then never
            # sends and never closes blocks this single-threaded read
            # forever, wedging the whole server for every other client.
            connection.settimeout(CONNECTION_TIMEOUT_SECS)
            with connection:
                try:
                    with connection.makefile("rb") as stream:
                        request = decode_request(stream)
                    text = transcriber.transcribe(
                        request.audio, request.language, request.initial_prompt or None
                    )
                    _tcp_send(connection, encode_response(text))
                except (RemoteError, OSError, ValueError) as error:
                    logger.warning("request from %s failed: %s", peer, error)
                    _tcp_send(connection, encode_error(str(error)))
    finally:
        listener.close()


def _tcp_send(connection: socket.socket, payload: bytes) -> None:
    """Reply to a peer, tolerating one that has already gone away.

    A client that disconnects before reading its reply makes sendall raise, and
    on the error path that second failure would otherwise escape the accept loop
    and kill the whole single-threaded server. This is the same guard the Unix
    daemon applies in Daemon._send.
    """
    try:
        connection.sendall(payload)
    except OSError as error:
        logger.debug("reply not delivered, peer gone: %s", error)


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
    recorder = StreamRecorder(device, effective)
    daemon = Daemon(
        transcriber=transcriber,
        recorder=recorder,
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
        recorder.close()
        pid_path.unlink(missing_ok=True)
    return 0
