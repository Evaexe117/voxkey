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
from voxkey.ipc.client import dictate_once
from voxkey.ipc.protocol import DictationRequest
from voxkey.languages import NAMES, language_name
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
    subparsers.add_parser("gui", help="open the control window")
    subparsers.add_parser("tray", help="run the tray icon")
    return parser


def _command_once(config_language: str) -> int:
    request = DictationRequest(
        language=config_language, initial_prompt=hints.load_hints()
    )
    # DaemonUnavailableError is a RuntimeError, so catching RuntimeError also
    # covers an error reply from the daemon; OSError covers a mid-request
    # disconnect. Either way this scripting entry point must print a line and
    # exit, never a traceback.
    try:
        text = dictate_once(paths.socket_file(), request)
    except (RuntimeError, OSError) as error:
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
    # A code voxkey does not recognise is not fatal (Whisper accepts many codes
    # beyond the name table), but warn so a typo surfaces here rather than as a
    # transcription failure later.
    if target.casefold() not in NAMES:
        print(
            _("Warning: {code} is not a known language code").format(code=target),
            file=sys.stderr,
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


def _launch(module_name: str, human_name: str) -> int:
    """Import a GTK entry point lazily and run it.

    GTK is an optional extra, so a missing PyGObject or AppIndicator namespace
    (both surface as ImportError here) prints one line naming the extra, never a
    traceback, and leaves ``voxkey serve`` on a headless box unaffected.
    """
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        print(
            f"{human_name} needs the optional GUI support: install it with "
            f"'pip install voxkey[gui]' and the system GTK and AppIndicator "
            f"libraries ({error})",
            file=sys.stderr,
        )
        return 1
    run = module.run
    return int(run())


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
            try:
                return runtime.run_serve(
                    config, listen=args.listen, remote=args.remote
                )
            except (ValueError, OverflowError, OSError) as error:
                # A malformed --listen/--remote (bad shape, or a port out of
                # range) raises ValueError/OverflowError; a bind()/listen()
                # failure (e.g. "Address already in use", or an IPv6 loopback
                # the AF_INET socket cannot bind) raises OSError. Either way,
                # print a line and exit rather than a startup traceback.
                print(str(error), file=sys.stderr)
                return 1
        case "listen":
            try:
                return run_listen(config)
            except (ValueError, NoKeyboardError, OSError) as error:
                # OSError covers the keyboard disconnecting mid-read (evdev
                # raises ENODEV): print a line and exit rather than a traceback,
                # matching how the daemon handles the microphone vanishing.
                print(str(error), file=sys.stderr)
                return 1
        case "devices":
            return runtime.run_devices()
        case "gui":
            return _launch("voxkey.gui.app", "the control window")
        case "tray":
            return _launch("voxkey.tray.app", "the tray icon")
        case _:
            parser.print_help(sys.stderr)
            return 2
