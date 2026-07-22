from __future__ import annotations

import pytest

from voxkey.cli import build_parser, main


def test_every_documented_subcommand_parses() -> None:
    parser = build_parser()
    for command in ("serve", "listen", "once", "lang", "stop", "devices"):
        assert parser.parse_args([command]).command == command


def test_serve_accepts_listen_and_remote() -> None:
    parser = build_parser()
    assert parser.parse_args(["serve", "--listen", "0.0.0.0:5555"]).listen == (
        "0.0.0.0:5555"
    )
    assert parser.parse_args(["serve", "--remote", "10.0.0.2:5555"]).remote == (
        "10.0.0.2:5555"
    )


def test_listen_and_remote_are_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["serve", "--listen", "0.0.0.0:1", "--remote", "h:2"])


def test_lang_takes_an_optional_code() -> None:
    parser = build_parser()
    assert parser.parse_args(["lang"]).code is None
    assert parser.parse_args(["lang", "fr"]).code == "fr"


def test_options_belonging_to_serve_are_rejected_elsewhere() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["once", "--listen", "0.0.0.0:5555"])


def test_no_command_prints_help_and_fails() -> None:
    assert main([]) == 2


def test_version_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "voxkey" in capsys.readouterr().out
