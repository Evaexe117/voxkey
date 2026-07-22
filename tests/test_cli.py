from __future__ import annotations

from pathlib import Path

import pytest

from voxkey import paths
from voxkey.cli import _command_stop, _signal_daemon, build_parser, main


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


def test_signal_daemon_returns_false_when_the_pid_file_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr("os.kill", lambda pid, sig: calls.append(pid))  # noqa: ARG005
    assert _signal_daemon(tmp_path / "missing.pid") is False
    assert calls == []


def test_signal_daemon_targets_the_pid_in_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "os.kill", lambda pid, sig: calls.append((pid, sig))
    )
    pid_file = tmp_path / "voxkey.pid"
    pid_file.write_text("4242")
    assert _signal_daemon(pid_file) is True
    assert len(calls) == 1
    signalled_pid, signalled_signal = calls[0]
    assert signalled_pid == 4242
    import signal as signal_module

    assert signalled_signal == signal_module.SIGTERM


def test_signal_daemon_returns_false_when_the_process_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _kill(pid: int, sig: int) -> None:  # noqa: ARG001
        raise ProcessLookupError

    monkeypatch.setattr("os.kill", _kill)
    pid_file = tmp_path / "voxkey.pid"
    pid_file.write_text("4242")
    assert _signal_daemon(pid_file) is False


def test_command_stop_signals_the_daemon_and_leaves_no_recording_stop_file(
    xdg: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr("os.kill", lambda pid, sig: calls.append(pid))  # noqa: ARG005
    paths.pid_file().parent.mkdir(parents=True, exist_ok=True)
    paths.pid_file().write_text("4242")
    assert _command_stop() == 0
    assert calls == [4242]
    assert not paths.stop_file().exists()


def test_command_stop_reports_when_the_daemon_is_not_running(
    xdg: Path,  # noqa: ARG001
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _command_stop() == 1
    assert "not running" in capsys.readouterr().err
