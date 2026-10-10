"""Stable CLI entrypoint: discovery, configuration and actionable error boundaries."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import logging
import os
import sys

from creative_research import __version__
from creative_research.cli.console import Console
from creative_research.cli.registry import COMMAND_SPECS, COMMANDS
from creative_research.cli.runtime import run_stage
from creative_research.cli.workspace import (
    cmd_adopt,
    cmd_doctor,
    cmd_init,
    cmd_status,
    cmd_validate,
)
from creative_research.errors import ApplicationError, ExitCode
from creative_research.infrastructure.config import RuntimeSettings, load_env_file, project_context
from creative_research.infrastructure.logging import logging_context, redact
from creative_research.infrastructure.paths import resolve_path

logger = logging.getLogger(__name__)


def _global_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--root", help="Resolve project paths against this root.")
    parser.add_argument(
        "--env-file", help="Load an explicit KEY=value file; process variables win."
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--verbose", "-v", action="store_true", help="Debug logging on stderr.")
    verbosity.add_argument("--quiet", "-q", action="store_true", help="Suppress human stdout.")
    parser.add_argument("--log-format", choices=("text", "json"), default=None)
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--version", "-V", action="store_true")
    return parser


def print_help(console: Console | None = None) -> None:
    console = console or Console()
    console.heading(f"Creative Research {__version__}")
    console.write("Evidence-backed research. Offline builds; paid provider calls are explicit.")
    console.write()
    console.write("Usage: creative-research [global options] <command> [command options]")
    groups = dict.fromkeys(spec.group for spec in COMMAND_SPECS)
    for group in groups:
        console.write()
        console.heading(group)
        console.rows((spec.name, spec.description) for spec in COMMAND_SPECS if spec.group == group)
    console.write()
    console.heading("Global options")
    console.rows(
        (
            ("--root PATH", "Project root; otherwise environment override or current directory."),
            ("--env-file PATH", "Explicit environment file. Never auto-loads or executes .env."),
            (
                "--verbose / --quiet",
                "Debug stderr logs / suppress human stdout; --json data stays visible.",
            ),
            ("--log-format text|json", "Structured JSON logs for CI; logs always go to stderr."),
            ("--color auto|always|never", "TTY-only colors by default; respects NO_COLOR."),
            ("--help / --version", "Discover commands or show the installed version."),
        )
    )
    console.write()
    console.heading("Quick start")
    for example in (
        "creative-research init",
        "creative-research doctor --json",
        "creative-research demo --out ./demo-workspace",
        "creative-research intelligence-build --dry-run --json",
        "creative-research --root /path/to/project intelligence-build",
        "creative-research lab --read-only --open",
        "creative-research <command> --help",
    ):
        console.write("  " + example)


def dispatch_stage(command: str, args: list[str]) -> int:
    run_stage(COMMANDS[command], args, prog=f"creative-research {command}")
    return ExitCode.OK


def _dispatch(args: list[str]) -> int:
    command, rest = args[0], args[1:]
    if command in COMMANDS:
        return dispatch_stage(command, rest)
    if command == "init":
        return cmd_init(rest)
    if command == "doctor":
        return cmd_doctor(rest)
    if command == "status":
        return cmd_status(rest)
    if command == "validate":
        return cmd_validate(rest)
    if command == "adopt":
        return cmd_adopt(rest)
    matches = difflib.get_close_matches(command, [spec.name for spec in COMMAND_SPECS], n=1)
    hint = f"Did you mean {matches[0]!r}?" if matches else "Run creative-research --help."
    raise ApplicationError(
        f"Unknown command {command!r}.", code="unknown_command", hint=hint, exit_code=ExitCode.USAGE
    )


def execute(argv: list[str] | None = None) -> int:
    """Library-friendly entrypoint: return a status, restore logging/project context."""
    argv = sys.argv[1:] if argv is None else argv
    console = Console(sys.stderr)
    verbose = False
    try:
        options, rest = _global_parser().parse_known_args(argv)
        verbose = options.verbose
        console = Console(sys.stderr, color=options.color)
        if options.version:
            print(__version__)
            return ExitCode.OK
        if not rest or rest[0] in {"--help", "-h"}:
            print_help(Console(color=options.color))
            return ExitCode.OK
        root = resolve_path(options.root) if options.root else None
        with project_context(root):
            if options.env_file:
                load_env_file(resolve_path(options.env_file))
            settings = RuntimeSettings.from_environ()
            level = "DEBUG" if verbose else "WARNING" if options.quiet else settings.log_level
            log_format = options.log_format or settings.log_format
            with logging_context(level=level, log_format=log_format, stream=sys.stderr):
                logger.debug("command_started", extra={"context": {"command": rest[0]}})
                machine_output = "--json" in rest or "--help" in rest or "-h" in rest
                if options.quiet and not machine_output:
                    with open(os.devnull, "w", encoding="utf-8") as sink:
                        with contextlib.redirect_stdout(sink):
                            return _dispatch(rest)
                return _dispatch(rest)
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            return int(exc.code or 0)
        console.error(str(exc.code), hint="Run the command with --help for input requirements.")
        return ExitCode.USAGE
    except BrokenPipeError:
        return ExitCode.OK
    except KeyboardInterrupt:
        console.error("Interrupted. Completed files and checkpoints are retained.")
        return ExitCode.INTERRUPTED
    except ApplicationError as exc:
        console.error(str(exc), hint=exc.hint)
        return exc.exit_code
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        console.error(str(exc), hint="Check configuration and paths; use --help or doctor.")
        if verbose:
            console.write(redact(str(exc)))
        return ExitCode.USAGE
    except Exception as exc:
        console.error(
            str(exc), hint="Retry with --verbose for debugging; see docs/troubleshooting.md."
        )
        if verbose:
            import traceback

            console.write(traceback.format_exc())
        return ExitCode.FAILED


def main() -> None:
    raise SystemExit(execute())


if __name__ == "__main__":
    main()
