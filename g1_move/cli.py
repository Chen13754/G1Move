"""Command-line and interactive clients for the native G1 movement wrapper."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from contextvars import ContextVar
from dataclasses import asdict
import json
import math
from pathlib import Path
import shlex
import sys
from typing import Any, Sequence, TextIO

from . import G1Move, MotionConfig, MotionError


_RESULT_STDOUT: ContextVar[TextIO | None] = ContextVar("g1_cli_result_stdout", default=None)


class _ArgumentError(ValueError):
    """An argument error that is rendered as JSON by the entry point."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _positive_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("distance and angle must be numbers, not booleans")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("distance and angle must be finite positive numbers") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError("distance and angle must be finite positive numbers")
    return number


def _validate_action(kind: Any, direction: Any, value: Any) -> tuple[str, str, float]:
    if kind == "move":
        directions = ("forward", "backward", "left", "right")
    elif kind == "turn":
        directions = ("left", "right")
    else:
        raise ValueError("action kind must be 'move' or 'turn'")
    if direction not in directions:
        raise ValueError(f"{kind} direction must be one of: {', '.join(directions)}")
    return kind, direction, _positive_number(value)


def _load_sequence(path: str) -> list[tuple[str, str, float]]:
    try:
        actions = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read sequence file {path!r}: {exc}") from exc
    if not isinstance(actions, list) or not actions:
        raise ValueError("sequence file must contain a non-empty JSON array of action triples")
    validated = []
    for index, action in enumerate(actions):
        if not isinstance(action, list) or len(action) != 3:
            raise ValueError(f"sequence action {index + 1} must be [kind, direction, value]")
        if isinstance(action[2], bool) or not isinstance(action[2], (int, float)):
            raise ValueError(f"sequence action {index + 1}: value must be a JSON number")
        try:
            validated.append(_validate_action(*action))
        except ValueError as exc:
            raise ValueError(f"sequence action {index + 1}: {exc}") from exc
    return validated


def _add_commands(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="command")
    move = commands.add_parser("move", help="move forward/backward/left/right by meters")
    move.add_argument("direction", choices=("forward", "backward", "left", "right"))
    move.add_argument("value", metavar="METERS")
    turn = commands.add_parser("turn", help="turn left/right by degrees")
    turn.add_argument("direction", choices=("left", "right"))
    turn.add_argument("value", metavar="DEGREES")
    sequence = commands.add_parser("sequence", help="execute action triples from a JSON file")
    sequence.add_argument("file", metavar="JSON_FILE")
    commands.add_parser("stop", help="send a zero-velocity command")
    commands.add_parser("shell", help="read commands until quit or EOF")


def _parser() -> _Parser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--backend", choices=("mock", "unitree"), default="mock")
    parser.add_argument("--interface", help="network interface for the Unitree backend")
    parser.add_argument("--dds-domain", type=int, default=0,
                        help="nonnegative DDS domain ID (default: 0; local simulation: 1)")
    parser.add_argument("--config", help="path to the movement configuration JSON")
    parser.add_argument("--mock-fast", action="store_true", help="skip timed waits (mock only)")
    _add_commands(parser)
    return parser


def _prepare(args: argparse.Namespace) -> Any:
    """Validate the whole submitted command before opening a robot connection."""
    if args.command in ("move", "turn"):
        return _validate_action(args.command, args.direction, args.value)
    if args.command == "sequence":
        return _load_sequence(args.file)
    return None


def _emit(value: Any, *, error: bool = False) -> None:
    print(json.dumps(value, ensure_ascii=False, allow_nan=False),
          file=sys.stderr if error else (_RESULT_STDOUT.get() or sys.stdout), flush=True)


def _emit_error(exc: BaseException) -> None:
    _emit({"error": str(exc), "error_type": type(exc).__name__}, error=True)


def _dispatch(robot: G1Move, command: str, prepared: Any) -> None:
    if command == "move":
        _emit(asdict(robot.move(prepared[1], prepared[2])))
    elif command == "turn":
        _emit(asdict(robot.turn(prepared[1], prepared[2])))
    elif command == "sequence":
        _emit([asdict(result) for result in robot.run_sequence(prepared)])
    elif command == "stop":
        robot.stop()
        _emit({"status": "stop_requested"})
    else:
        raise ValueError(f"unsupported command: {command}")


_SHELL_HELP = {
    "commands": [
        "move forward|backward|left|right METERS",
        "turn left|right DEGREES",
        'sequence "path/to/actions.json"',
        "stop", "help", "quit",
    ],
    "interrupt": "Ctrl+C during an action stops that action; Ctrl+C while idle exits.",
}


def _shell(robot: G1Move) -> None:
    parser = _Parser(prog="g1-move", add_help=False)
    _add_commands(parser)
    interactive = sys.stdin.isatty()
    if interactive:
        print("G1 movement shell. Type help for commands; quit to exit.", file=sys.stderr)
    while True:
        try:
            if interactive:
                print("g1> ", end="", file=sys.stderr, flush=True)
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            if interactive:
                print(file=sys.stderr)
            return
        if not line:
            return
        try:
            lexer = shlex.shlex(line, posix=True)
            lexer.whitespace_split = True
            lexer.commenters = ""
            # Preserve backslashes in Windows paths, including quoted paths.
            lexer.escape = ""
            tokens = list(lexer)
            if not tokens:
                continue
            if tokens == ["quit"] or tokens == ["exit"]:
                return
            if tokens in (["help"], ["--help"], ["-h"]):
                _emit(_SHELL_HELP)
                continue
            args = parser.parse_args(tokens)
            if args.command == "shell":
                raise ValueError("already in the interactive shell")
            prepared = _prepare(args)
            _dispatch(robot, args.command, prepared)
        except KeyboardInterrupt:
            # Core execution also stops in its cleanup path. An explicit stop
            # here covers interrupts before dispatch reaches the core.
            try:
                robot.stop()
            except MotionError as exc:
                _emit_error(exc)
            else:
                _emit({"status": "stop_requested", "reason": "keyboard_interrupt"})
        except (ValueError, MotionError) as exc:
            _emit_error(exc)
        except SystemExit as exc:
            # argparse's per-command --help must not terminate the shell.
            if exc.code:
                _emit_error(ValueError("invalid shell command"))


def _main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.mock_fast and args.backend != "mock":
            raise ValueError("--mock-fast is only available with --backend mock")
        if args.backend == "unitree" and not args.interface:
            raise ValueError("--interface is required with --backend unitree")
        prepared = _prepare(args)
        config = MotionConfig.from_file(args.config) if args.config else MotionConfig()
        # Unitree DDS prints some diagnostics directly to stdout. Keep those
        # on stderr while JSON results use the stream captured by main().
        # Argument parsing stays outside this context so --help remains normal.
        with redirect_stdout(sys.stderr), G1Move(
            backend=args.backend, interface=args.interface, config=config,
            dds_domain=args.dds_domain,
            mock_realtime=not args.mock_fast,
        ) as robot:
            try:
                if args.command in (None, "shell"):
                    _shell(robot)
                else:
                    _dispatch(robot, args.command, prepared)
            except KeyboardInterrupt:
                try:
                    robot.stop()
                except MotionError as exc:
                    _emit_error(exc)
                _emit({"error": "interrupted", "error_type": "KeyboardInterrupt"}, error=True)
                return 130
        return 0
    except KeyboardInterrupt:
        _emit({"error": "interrupted", "error_type": "KeyboardInterrupt"}, error=True)
        return 130
    except (ValueError, OSError) as exc:
        _emit_error(exc)
        return 2
    except MotionError as exc:
        _emit_error(exc)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI, returning 0, 1 (SDK), 2 (input), or 130 (interrupt)."""
    token = _RESULT_STDOUT.set(sys.stdout)
    try:
        return _main(argv)
    finally:
        _RESULT_STDOUT.reset(token)
