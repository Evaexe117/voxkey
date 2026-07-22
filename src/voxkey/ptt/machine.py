"""When a key hold counts as a dictation.

The push-to-talk key is also a modifier. With the RIGHTCTRL default, every
Ctrl+V paste retriggers a recording; those phantom presses last a few tenths of
a second, and Whisper fills the silence with subtitle boilerplate, which then
overwrites the clipboard the paste had just consumed.

A phrase blacklist is not enough, because observed hallucinations include text
that is not on any list. The duration is the reliable signal: every measured
press under 0.6 s was a phantom, and the shortest genuine dictation was 2.0 s.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

MIN_HOLD_SECS = 1.0


@dataclass(frozen=True)
class KeyEvent:
    pressed: bool
    timestamp: float


class HoldDecision(Enum):
    START = auto()
    ACCEPT = auto()
    DISCARD = auto()
    IGNORE = auto()


class HoldMachine:
    """Turn a stream of key events into start, accept and discard decisions."""

    def __init__(self, min_hold_secs: float = MIN_HOLD_SECS) -> None:
        self._min_hold_secs = min_hold_secs
        self._pressed_at: float | None = None

    @property
    def holding(self) -> bool:
        return self._pressed_at is not None

    def feed(self, event: KeyEvent) -> HoldDecision:
        if event.pressed:
            if self._pressed_at is not None:
                return HoldDecision.IGNORE
            self._pressed_at = event.timestamp
            return HoldDecision.START
        if self._pressed_at is None:
            return HoldDecision.IGNORE
        held_for = event.timestamp - self._pressed_at
        self._pressed_at = None
        if held_for >= self._min_hold_secs:
            return HoldDecision.ACCEPT
        return HoldDecision.DISCARD
