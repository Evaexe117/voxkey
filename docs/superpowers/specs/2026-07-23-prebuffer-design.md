# voxkey pre-buffer: faithful port of dictate's persistent rolling buffer

Date: 2026-07-23
Status: approved, awaiting implementation

## Why

voxkey is a faithful rewrite of `dictate`, which the user considers excellent.
One behaviour was not yet ported and is currently dead code: the rolling
pre-buffer. In `dictate` it is what removes the start-of-dictation delay, so the
first words spoken in the instant before recording truly begins are still
captured. The user has decided voxkey must replicate it exactly.

## How dictate does it (the behaviour to match)

`dictate`'s daemon opens **one persistent audio stream** that stays open the
whole time the daemon runs (`prebuf_stream`, `dictate` lines 509-555). Its
callback always appends the newest block to a rolling `deque` that keeps only
the last `pre_buffer_secs` of audio; older audio is discarded continuously.
When a dictation starts, it snapshots that deque (`list(pre_buffer)`), and when
the recording ends it prepends the snapshot to the captured audio (`dictate`
line 776, "Prepend pre-buffer to recorded audio").

**Consequence, explicitly accepted by the user:** the microphone device is open
continuously while the daemon runs. Nothing leaves the machine; only the last
`pre_buffer_secs` is ever retained, constantly overwritten. This is the same
property `dictate` already has.

## Design

Two units, keeping the voxkey rule that decision logic is pure and the device
is a thin shell.

### `ContinuousCapture` (pure, in `audio/capture.py`)

Holds the rolling pre-buffer and, while armed, accumulates a recording that
begins with the pre-buffer snapshot. Driven one block at a time, so every
branch is tested with synthetic signals and no device.

```
ContinuousCapture(pre_buffer_secs: float, sample_rate: int = SAMPLE_RATE)

pump(block: NDArray[float32], now: float) -> None
    Always append block to the rolling pre-buffer. If armed and not finished,
    also append block to the recording and feed the SilenceDetector with
    rms(block) at time `now`; if the detector says stop, mark finished.

arm(detector: SilenceDetector) -> None
    Snapshot the current pre-buffer as the first chunk of the recording, adopt
    the detector, clear the finished flag. `now` passed to subsequent pump calls
    is measured from the moment of arm (the driver resets its clock origin).

property armed: bool
property finished: bool

result() -> NDArray[float32] | None
    None when no detector or the detector never detected speech. Otherwise the
    concatenation of the pre-buffer snapshot and every recorded block.

mark_finished() -> None
    Force finished (used for a manual stop, which counts as a valid recording
    regardless of levels — set detector.speech_detected as well).

disarm() -> None
    Drop the detector and the recording buffer, keep the rolling pre-buffer
    running for the next dictation.
```

`PreBuffer` gains a `snapshot() -> NDArray[float32]` that copies its current
contents without clearing (the buffer must keep rolling); `drain()` stays for
existing callers.

The clock contract is the same as `record_utterance`: `now` reads 0 at arm and
increases, so `SilenceDetector`'s wait window is measured from the start of the
recording, not from stream start.

### `StreamRecorder` rewrite (thin shell, in `runtime.py`)

Owns the persistent stream and the background reader thread; satisfies the
existing `Recorder` Protocol so the daemon is unchanged.

- `__init__`: calibrate as today, build `ContinuousCapture(config.pre_buffer_secs)`,
  start a daemon reader thread that pulls blocks from one persistent
  `StreamAudioSource` and calls `pump` under a lock, tagging each block with
  `now = monotonic() - arm_origin`.
- `record(wait_secs, silence_secs)`: build a `SilenceDetector`, under the lock
  set `arm_origin = monotonic()` and `arm(detector)`, then wait until the
  capture reports finished or `stop_requested()` fires (manual stop →
  `mark_finished`), then read `result()` and `disarm()`, all under the lock.
- `close()`: signal the reader thread to stop and join it; called when the
  daemon shuts down so no thread and no open stream leak. `run_serve` calls it
  in its `finally`, next to the pid-file cleanup.

The reader thread is the only new concurrency. The lock guards the shared
capture state between the reader and `record`. There is exactly one recording
at a time (one microphone, the daemon serves one request at a time), so there
is no contention beyond the single reader/consumer pair.

## Testing

- `ContinuousCapture` fully unit-tested with synthetic blocks and a manual
  clock: pre-buffer prepended, snapshot does not clear the rolling buffer,
  silence stops the recording, no-speech yields None, manual stop counts,
  disarm keeps the buffer rolling for a second dictation, the pre-buffer only
  keeps the last window.
- `PreBuffer.snapshot` tested: returns the last window without clearing.
- `StreamRecorder`'s thread is not unit-tested against a real device (no mic in
  CI); instead the reader loop is factored so its per-block step is the same
  `pump` call the pure tests cover, and a small test drives `StreamRecorder`
  with a fake persistent source to confirm arm/wait/result/close wiring and
  that `close()` joins the thread with no leak.
- `config.pre_buffer_secs` becomes a live setting again; a test confirms it
  sizes the buffer.

## Out of scope

- dictate's mic-health monitor that re-calibrates on reconnect. It is a
  separate robustness feature, not the pre-buffer, and is not ported here.
