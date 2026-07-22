from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from voxkey.config import Config, ConfigError, load, parse


def test_defaults_are_english_first() -> None:
    config = parse({})
    assert config.language == "en"
    assert config.languages == ("en", "fr")
    assert config.key == "RIGHTCTRL"
    assert config.pre_buffer_secs == 1.0
    assert config.silence_secs == 3.0
    assert config.wait_secs == 10.0
    assert config.log_transcripts is False
    assert config.model is None
    assert config.remote is None


def test_values_override_defaults() -> None:
    config = parse({"language": "fr", "key": "PAUSE", "silence_secs": 2})
    assert config.language == "fr"
    assert config.key == "PAUSE"
    assert config.silence_secs == 2.0


def test_integer_is_accepted_where_a_float_is_expected() -> None:
    assert parse({"wait_secs": 5}).wait_secs == 5.0


def test_bool_is_rejected_where_a_float_is_expected() -> None:
    with pytest.raises(ConfigError, match="wait_secs"):
        parse({"wait_secs": True})


def test_unknown_key_names_itself_and_the_known_keys() -> None:
    with pytest.raises(ConfigError) as excinfo:
        parse({"langauge": "fr"})
    message = str(excinfo.value)
    assert "langauge" in message
    assert "language" in message


def test_wrong_type_names_key_expected_and_actual() -> None:
    with pytest.raises(ConfigError) as excinfo:
        parse({"silence_secs": "three"})
    message = str(excinfo.value)
    assert "silence_secs" in message
    assert "number" in message
    assert "str" in message


def test_empty_language_list_is_rejected() -> None:
    with pytest.raises(ConfigError, match="languages"):
        parse({"languages": []})


def test_non_positive_durations_are_rejected() -> None:
    for key in ("pre_buffer_secs", "silence_secs", "wait_secs"):
        with pytest.raises(ConfigError, match=key):
            parse({key: 0})


def test_remote_must_look_like_host_port() -> None:
    assert parse({"remote": "10.0.0.2:5555"}).remote == "10.0.0.2:5555"
    with pytest.raises(ConfigError, match="remote"):
        parse({"remote": "10.0.0.2"})


def test_load_returns_defaults_when_the_file_is_absent(xdg: Path) -> None:  # noqa: ARG001
    assert load() == Config()


def test_load_reads_the_config_file(xdg: Path) -> None:  # noqa: ARG001
    from voxkey import paths

    config_file = paths.config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        textwrap.dedent(
            """
            language = "fr"
            languages = ["fr", "en"]
            key = "PAUSE"
            """
        )
    )
    config = load()
    assert config.language == "fr"
    assert config.languages == ("fr", "en")
    assert config.key == "PAUSE"


def test_load_reports_the_path_on_malformed_toml(xdg: Path) -> None:  # noqa: ARG001
    from voxkey import paths

    config_file = paths.config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("language = ")
    with pytest.raises(ConfigError) as excinfo:
        load()
    assert str(paths.config_file()) in str(excinfo.value)


def test_nan_duration_is_rejected() -> None:
    for key in ("pre_buffer_secs", "silence_secs", "wait_secs"):
        with pytest.raises(ConfigError, match="finite"):
            parse({key: float("nan")})


def test_infinite_duration_is_rejected() -> None:
    for key in ("pre_buffer_secs", "silence_secs", "wait_secs"):
        with pytest.raises(ConfigError, match="finite"):
            parse({key: float("inf")})
