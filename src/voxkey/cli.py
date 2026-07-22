"""The voxkey command line.

Subcommands rather than flags, so each mode owns its options and its help. This
module only parses and dispatches; it holds no behaviour of its own.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from voxkey import __version__, hints, paths, runtime, state
from voxkey.config import ConfigError, load
from voxkey.i18n import _, setup
from voxkey.ipc.client import DaemonUnavailableError, dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.languages import language_name
from voxkey.ptt.keyboard import NoKeyboardError
from voxkey.ptt.runner import run_listen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voxkey",
        description="Push-to-talk dictation for Linux, transcribed locally.",
    )
    parser.add_argument("--version", action="version", version=f"voxkey {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log at debug level"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    serve = subparsers.add_parser(
        "serve", help="run the daemon, keeping the model resident"
    )
    target = serve.add_mutually_exclusive_group()
    target.add_argument(
        "--listen", metavar="HOST:PORT", help="run as a headless transcription server"
    )
    target.add_argument(
        "--remote", metavar="HOST:PORT", help="record here, transcribe on that server"
    )

    subparsers.add_parser("listen", help="run the push-to-talk client")
    subparsers.add_parser("once", help="one dictation, text on standard output")

    lang = subparsers.add_parser("lang", help="cycle or set the transcription language")
    lang.add_argument("code", nargs="?", help="language code, or omit to cycle")

    subparsers.add_parser("stop", help="stop the daemon")
    subparsers.add_parser("devices", help="list audio devices and keyboards")
    return parser


def _command_once(config_language: str) -> int:
    request = DictationRequest(
        language=config_language, initial_prompt=hints.load_hints()
    )
    try:
        text = dictate_once(paths.socket_file(), request)
    except DaemonUnavailableError as error:
        print(str(error), file=sys.stderr)
        return 1
    if not text:
        print(_("No speech detected"), file=sys.stderr)
        return 1
    print(text)
    return 0


def _command_lang(
    code: str | None, config_language: str, languages: Sequence[str]
) -> int:
    target = (
        code if code is not None else state.next_language(config_language, languages)
    )
    state.set_language(target)
    print(
        _("Language: {name} ({code})").format(name=language_name(target), code=target)
    )
    return 0


def _signal_daemon(pid_path: Path) -> bool:
    """Send SIGTERM to the daemon named by ``pid_path``.

    Returns True if a live process was signalled, False if the daemon is not
    running: no pid file, or the process behind it is already gone.
    """
    try:
        pid = int(pid_path.read_text().strip())
    except (OSError, ValueError):
        return False
    # A pid of 0 or negative would signal a whole process group, and a
    # corrupted file must never be trusted that far.
    if pid <= 0:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A stale pid file whose number was reused by another user's process:
        # not our daemon, so report it as not running rather than crashing.
        return False
    return True


def _command_stop() -> int:
    if not _signal_daemon(paths.pid_file()):
        print("the voxkey daemon is not running", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    try:
        config = load()
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    setup()
    language = state.get_language(config)

    match args.command:
        case "once":
            return _command_once(language)
        case "lang":
            return _command_lang(args.code, language, config.languages)
        case "stop":
            return _command_stop()
        case "serve":
            return runtime.run_serve(config, listen=args.listen, remote=args.remote)
        case "listen":
            try:
                return run_listen(config)
            except (ValueError, NoKeyboardError) as error:
                print(str(error), file=sys.stderr)
                return 1
        case "devices":
            return runtime.run_devices()
        case _:
            parser.print_help(sys.stderr)
            return 2
