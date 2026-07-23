# Security policy

## Supported version

The latest commit on `master`. There is no release branch and no backporting.

## Reporting a vulnerability

Open a private security advisory on GitHub: Security tab of the repository,
"Report a vulnerability" button. Please do not open a public issue.

Response time is best effort: this is a spare-time project maintained by one
person.

## Scope

Worth reporting:

- Any way audio or transcribed text leaves the machine outside the explicit
  `--listen`/`--remote` streaming mode. In local mode voxkey must never open
  a network socket: transcription is local by design.
- Any keystroke information used, retained, or logged beyond detecting the
  configured push-to-talk key. The client reads every keyboard through evdev,
  so anything that turns it into a keylogger is critical.
- An escape from the vocabulary-hints directories: a symlink or path inside
  `~/.config/voxkey/hints.d/` or a project's `.voxkey-hints.d/` must not
  cause a file outside those directories to be read and fed to the model.
- Command injection through configuration values, language codes, or
  transcript content reaching `xsel` or any other subprocess.
- Another local account being able to talk to the daemon's Unix socket,
  trigger or read a recording, or read the configuration or the optional
  transcript log.
- A transcript persisted anywhere while `log_transcripts` is false.

Expected behaviour, not vulnerabilities:

- `--listen`/`--remote` streaming raw, unencrypted 16 kHz audio over TCP.
  This is documented; it is meant for trusted networks or an SSH tunnel or
  VPN.
- The microphone staying open while the daemon runs. That is what makes the
  rolling pre-buffer possible.
- The push-to-talk client requiring membership of the `input` group, which by
  nature allows reading input devices on the machine.
