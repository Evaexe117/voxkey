"""Load and validate the user's configuration.

The current dictate script ignores unknown keys silently and lets a wrong type
crash deep inside the audio thread. Here every problem is reported at startup,
naming the key, what was expected and what was found.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from voxkey import paths


class ConfigError(ValueError):
    """The configuration file is unusable. The message names the key."""


@dataclass(frozen=True, slots=True)
class Config:
    language: str = "en"
    languages: tuple[str, ...] = ("en", "fr")
    model: str | None = None
    key: str = "RIGHTCTRL"
    pre_buffer_secs: float = 1.0
    silence_secs: float = 3.0
    wait_secs: float = 10.0
    log_transcripts: bool = False
    remote: str | None = None


_DURATION_KEYS = ("pre_buffer_secs", "silence_secs", "wait_secs")


def _known_keys() -> tuple[str, ...]:
    return tuple(field.name for field in fields(Config))


def _as_str(key: str, value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError(
            f"{key}: expected a string, found {type(value).__name__}"
        )
    return value


def _as_number(key: str, value: object) -> float:
    # bool is a subclass of int, and "silence_secs = true" is always a mistake.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"{key}: expected a number, found {type(value).__name__}"
        )
    number = float(value)
    # TOML allows nan and inf literals. NaN <= 0 is False, so without this a
    # non-finite duration slips past the positivity check and then disables the
    # silence detector (now - last_speech >= nan is never true).
    if not math.isfinite(number):
        raise ConfigError(f"{key}: expected a finite number, found {number}")
    return number


def _as_bool(key: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(
            f"{key}: expected true or false, found {type(value).__name__}"
        )
    return value


def _as_language_list(key: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{key}: expected a non-empty list of language codes")
    return tuple(_as_str(key, item) for item in value)


def _as_address(key: str, value: object) -> str:
    text = _as_str(key, value)
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ConfigError(f"{key}: expected HOST:PORT, found {text!r}")
    return text


def parse(raw: dict[str, object]) -> Config:
    """Validate a raw mapping and build a Config. Pure, so it is directly testable."""
    unknown = sorted(set(raw) - set(_known_keys()))
    if unknown:
        known = ", ".join(_known_keys())
        raise ConfigError(
            f"unknown configuration key(s): {', '.join(unknown)}. Known keys: {known}"
        )

    values: dict[str, object] = {}
    if "language" in raw:
        values["language"] = _as_str("language", raw["language"])
    if "languages" in raw:
        values["languages"] = _as_language_list("languages", raw["languages"])
    if "model" in raw:
        values["model"] = _as_str("model", raw["model"])
    if "key" in raw:
        values["key"] = _as_str("key", raw["key"])
    for key in _DURATION_KEYS:
        if key in raw:
            seconds = _as_number(key, raw[key])
            if seconds <= 0:
                raise ConfigError(f"{key}: expected a positive number, found {seconds}")
            values[key] = seconds
    if "log_transcripts" in raw:
        values["log_transcripts"] = _as_bool("log_transcripts", raw["log_transcripts"])
    if "remote" in raw:
        values["remote"] = _as_address("remote", raw["remote"])

    return Config(**values)  # type: ignore[arg-type]  # validated above


def load(path: Path | None = None) -> Config:
    """Read the configuration file, or return defaults when it does not exist."""
    target = path if path is not None else paths.config_file()
    try:
        raw_bytes = target.read_bytes()
    except FileNotFoundError:
        return Config()
    try:
        raw = tomllib.loads(raw_bytes.decode())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ConfigError(f"{target}: {error}") from error
    return parse(raw)
