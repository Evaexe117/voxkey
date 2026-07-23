"""The push-to-talk loop.

The loop is a pure consumer of key events and a Session, so the phantom press
behaviour is tested without a keyboard, a daemon or a clipboard. Only
``DaemonSession`` and ``run_listen`` touch the outside world.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Protocol

from voxkey import hints, paths, state
from voxkey.config import Config
from voxkey.ipc.client import dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.output import clipboard, sound
from voxkey.ptt.keyboard import key_events, resolve_key
from voxkey.ptt.machine import MIN_HOLD_SECS, HoldDecision, HoldMachine, KeyEvent

logger = logging.getLogger(__name__)


class Session(Protocol):
    def start(self) -> None:
        """Ask the daemon to begin recording."""

    def finish(self) -> str:
        """End the recording and return the transcribed text."""

    def abort(self) -> None:
        """End the recording and throw the result away."""


class FakeSession:
    """A Session for tests, recording the calls it received."""

    def __init__(self, texts: Sequence[str], fail_first: bool = False) -> None:
        self._texts = list(texts)
        self._index = 0
        self._fail_first = fail_first
        self.log: list[str] = []

    def start(self) -> None:
        self.log.append("start")

    def finish(self) -> str:
        self.log.append("finish")
        if self._fail_first:
            self._fail_first = False
            raise RuntimeError("daemon went away")
        text = self._texts[min(self._index, len(self._texts) - 1)]
        self._index += 1
        return text

    def abort(self) -> None:
        self.log.append("abort")


def run_push_to_talk(
    events: Iterable[KeyEvent],
    session: Session,
    deliver: Callable[[str], None],
    min_hold_secs: float = MIN_HOLD_SECS,
) -> None:
    """Turn key holds into delivered text. Never raises on a single failure."""
    machine = HoldMachine(min_hold_secs=min_hold_secs)
    for event in events:
        decision = machine.feed(event)
        try:
            match decision:
                case HoldDecision.START:
                    session.start()
                case HoldDecision.ACCEPT:
                    text = session.finish()
                    if text:
                        deliver(text)
                    else:
                        logger.info("nothing was said")
                case HoldDecision.DISCARD:
                    logger.info("press too short, discarded as a phantom")
                    session.abort()
                case HoldDecision.IGNORE:
                    pass
        except Exception:  # noqa: BLE001  # one bad dictation must not end the loop
            logger.exception("dictation failed, continuing")


class DaemonSession:
    """Session backed by the daemon over its Unix socket."""

    def __init__(self, socket_path: Path, config: Config) -> None:
        self._socket_path = socket_path
        self._config = config
        self._thread: threading.Thread | None = None
        self._text = ""
        self._error: BaseException | None = None

    def _dictate(self) -> None:
        # Read the language live for each dictation, so a `voxkey lang` switch
        # takes effect on the next hold rather than being frozen at client
        # start. This mirrors how sound.play reads the mute state live; the
        # language lives in the same runtime state file, not in config.
        language = state.get_language(self._config)
        try:
            self._text = dictate_once(
                self._socket_path,
                DictationRequest(
                    language=language, initial_prompt=hints.load_hints()
                ),
            )
        except BaseException as error:  # noqa: BLE001  # re-raised in finish
            self._error = error

    def start(self) -> None:
        self._text = ""
        self._error = None
        self._thread = threading.Thread(target=self._dictate, daemon=True)
        self._thread.start()

    def _join(self) -> None:
        # Releasing the key raises the stop flag; the daemon then stops
        # recording and answers, which lets the worker thread finish.
        state.write_atomic(paths.stop_file(), "stop")
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def finish(self) -> str:
        self._join()
        if self._error is not None:
            raise self._error
        return self._text

    def abort(self) -> None:
        self._join()
        # A phantom press throws the result away, but a genuine daemon failure
        # during it should still leave a trace rather than vanish silently.
        if self._error is not None:
            logger.warning("dictation failed during an aborted press: %s", self._error)


def deliver_to_clipboard(text: str) -> None:
    """Copy the transcript and chime according to whether the copy succeeded.

    The chime must reflect what actually happened: if the copy failed (xsel
    missing, for instance) the transcript is lost, so ring the warning sound
    rather than the "done" chime that would say it landed on the clipboard.
    """
    if clipboard.copy(text):
        sound.play(sound.SOUND_COMPLETE)
    else:
        sound.play(sound.SOUND_BELL)


def run_listen(config: Config) -> int:
    """Read the push-to-talk key and deliver dictations to the clipboard."""
    from voxkey.ptt.keyboard import find_keyboards

    key_code = resolve_key(config.key)
    device_path = find_keyboards()[0]
    session = DaemonSession(paths.socket_file(), config)

    logger.info("holding %s dictates, reading %s", config.key, device_path)
    run_push_to_talk(
        key_events(device_path, key_code), session, deliver_to_clipboard
    )
    return 0
