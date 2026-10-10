"""Portable, offline-only bridge to the separately installed Creative Research CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_MASTER = "data/05_master/creative_master.parquet"
DEFAULT_WORKSPACE = "data/07_exports/operator-intelligence"
MAX_OUTPUT_BYTES = 64 * 1024
STAGES = (
    "warehouse",
    "performance",
    "cadence",
    "families",
    "propagation",
    "timeline",
    "patterns",
    "strategies",
    "knowledge",
    "workspace",
    "audit",
    "outcome",
)


class BridgeError(ValueError):
    """Invalid input or unmet dependency; never contains a credential value."""


def clean_environment() -> dict[str, str]:
    """Do not pass credentials, Python import overrides or implicit engine settings."""
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env.update(NO_COLOR="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def redact(value: str) -> str:
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    for pattern in (
        r"apify_api_[\w-]+",
        r"AIza[\w-]{20,}",
        r"(?:ghp_|github_pat_)[\w-]+",
        r"(?i)(?:api[_-]?key|token|secret|password)\s*[=:]\s*[^\s,;]+",
    ):
        value = re.sub(pattern, "[REDACTED]", value)
    return value


def confined(root: Path, value: str, *, exists: bool = True) -> Path:
    path = Path(value).expanduser()
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root):
        raise BridgeError("Path must stay inside the explicit project root (including symlinks).")
    if exists and not path.is_file():
        raise BridgeError(
            f"Missing input: {path.relative_to(root)}. Run status; do not acquire data automatically."
        )
    return path


def workspace_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise BridgeError("Project root must be an existing directory; pass --root explicitly.")
    return root


def engine_python(value: str) -> str:
    executable = shutil.which(value)
    if executable is None:
        raise BridgeError("Engine Python not found. Pass --python /path/to/engine-venv/bin/python.")
    return executable


def run_process(argv: list[str], *, timeout: int, max_bytes: int) -> dict[str, Any]:
    """Drain both pipes concurrently with bounded memory, killing on deadline."""
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    sizes = {"stdout": 0, "stderr": 0}

    def drain(stream: Any, name: str) -> None:
        with stream:
            while chunk := stream.read(8192):
                sizes[name] += len(chunk)
                remaining = max_bytes - len(outputs[name])
                if remaining > 0:
                    outputs[name].extend(chunk[:remaining])

    with tempfile.TemporaryDirectory(prefix="creative-research-bridge-") as directory:
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(
            argv,
            cwd=directory,
            env=clean_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )

        def stop() -> None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass

        workers = [
            threading.Thread(target=drain, args=(process.stdout, "stdout")),
            threading.Thread(target=drain, args=(process.stderr, "stderr")),
        ]
        for worker in workers:
            worker.start()
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop()
            code = process.wait()
        except BaseException:
            stop()
            process.wait()
            raise
        finally:
            for worker in workers:
                worker.join(timeout=max(0, deadline - time.monotonic()))
            if any(worker.is_alive() for worker in workers):
                timed_out = True
                stop()
                for worker in workers:
                    worker.join()
    return {
        "exit_code": 124 if timed_out else 128 - code if code < 0 else code,
        "timed_out": timed_out,
        "stdout": redact(outputs["stdout"].decode("utf-8", errors="replace")),
        "stderr": redact(outputs["stderr"].decode("utf-8", errors="replace")),
        "truncated": any(size > max_bytes for size in sizes.values()),
        "output_bytes": sizes,
    }


def preflight(python: str) -> dict[str, Any]:
    result = run_process(
        [python, "-I", "-m", "creative_research", "--version"], timeout=30, max_bytes=4096
    )
    if result["exit_code"]:
        raise BridgeError(
            "Installed engine unavailable. Install with uv sync (checkout) or pip install /path/to/wheel; select that Python with --python. No installation was attempted."
        )
    if not re.fullmatch(r"1\.\d+\.\d+", result["stdout"].strip()):
        raise BridgeError("Unsupported engine version: this skill requires creative-research 1.x.")
    return result


def _table(root: Path, value: str) -> str:
    path = confined(root, value)
    if not path.relative_to(root).parts[0] == "data" or path.suffix not in {
        ".parquet",
        ".csv",
        ".jsonl",
    }:
        raise BridgeError("Query inputs must be .parquet/.csv/.jsonl tables inside data/.")
    if "operating_state" in path.relative_to(root).parts:
        raise BridgeError("Private operating state is outside this bridge's scope.")
    return str(path)


def _write_preflight(root: Path) -> None:
    """Reject redirecting generated outputs or private namespaces through symlinks."""
    for directory in (root / "data", root / "config"):
        if directory.exists():
            for path in (directory, *directory.rglob("*")):
                if path.is_symlink():
                    raise BridgeError(
                        "Build/audit writes require a workspace without data/config symlinks. Use a copied workspace; existing evidence was not changed."
                    )


def command_arguments(ns: argparse.Namespace, root: Path) -> list[str]:
    command = ns.command
    if command == "status":
        return [command, "--json"]
    if command == "validate":
        return [command, "--master", _table(root, ns.master), "--json"]
    if command == "query":
        result = [command, _table(root, ns.table), "--limit", str(ns.limit)]
        if ns.columns:
            if not re.fullmatch(r"[A-Za-z_][\w]*(?:,[A-Za-z_][\w]*)*", ns.columns):
                raise BridgeError("--columns expects comma-separated column names without spaces.")
            result += ["--columns", ns.columns]
        for condition in ns.where:
            if len(condition) > 500 or "\x00" in condition:
                raise BridgeError("Query condition is invalid or exceeds 500 characters.")
            if (
                not re.fullmatch(r"[A-Za-z_]\w*(?:>=|<=|!=|=|>|<).+", condition)
                or "==" in condition
            ):
                raise BridgeError(
                    "Use column=value, column!=value or numeric comparisons; equality is a single '=', not '=='."
                )
            result += ["--where", condition]
        return result
    if command == "rank-posts":
        return [
            command,
            _table(root, ns.master),
            "--rank",
            ns.rank,
            "--content-type",
            ns.content_type,
            "--top",
            str(ns.top),
        ]
    if command == "compare-cohorts":
        result = [
            command,
            "--group-by",
            ns.group_by,
            "--metric",
            ns.metric,
            "--max-groups",
            str(ns.max_groups),
            "--examples",
            str(ns.examples),
        ]
        for option in (
            "operator_id",
            "account_id",
            "family_id",
            "since",
            "until",
            "values",
            "content_type",
        ):
            value = getattr(ns, option, None)
            if value is not None:
                if len(value) > 500 or "\x00" in value:
                    raise BridgeError(
                        f"--{option.replace('_', '-')} is invalid or exceeds 500 characters."
                    )
                result += [f"--{option.replace('_', '-')}", value]
        return result
    if command == "trace-family":
        if not re.fullmatch(r"[A-Za-z0-9_:.~-]{1,200}", ns.family_id):
            raise BridgeError("Invalid family_id; use a canonical family identifier.")
        result = [
            command,
            "--family-id",
            ns.family_id,
            "--offset",
            str(ns.offset),
            "--limit",
            str(ns.limit),
            "--beats",
            str(ns.beats),
        ]
        if ns.operator_id is not None:
            if len(ns.operator_id) > 200 or "\x00" in ns.operator_id:
                raise BridgeError("Invalid operator_id.")
            result += ["--operator-id", ns.operator_id]
        return result
    if command in {"mechanic-groups", "trace-mechanic", "verify-pattern", "trace-strategy"}:
        result = [command]
        if command == "trace-strategy":
            if not re.fullmatch(r"[A-Za-z0-9_:.~-]{1,200}", ns.hypothesis_id):
                raise BridgeError("Invalid hypothesis ID")
            return [
                command,
                "--hypothesis-id",
                ns.hypothesis_id,
                "--offset",
                str(ns.offset),
                "--limit",
                str(ns.limit),
                "--max-patterns",
                str(ns.max_patterns),
            ]
        result += ["--metric", ns.metric, "--content-type", ns.content_type]
        for key in ("operator_id", "account_id"):
            value = getattr(ns, key, None)
            if value is not None:
                if len(value) > 200 or "\x00" in value:
                    raise BridgeError(f"Invalid {key}")
                result += [f"--{key.replace('_', '-')}", value]
        if command in {"mechanic-groups", "trace-mechanic"}:
            if not re.fullmatch(r"[a-z_,]{1,200}", ns.axes):
                raise BridgeError("Invalid --axes; select two or three known fields")
            result += ["--axes", ns.axes]
        if command == "mechanic-groups":
            result += [
                "--min-posts",
                str(ns.min_posts),
                "--max-groups",
                str(ns.max_groups),
                "--examples",
                str(ns.examples),
            ]
        elif command == "trace-mechanic":
            if not re.fullmatch(r"MECH-[A-F0-9]{16}", ns.mechanic_id):
                raise BridgeError("Invalid mechanic ID")
            result += [
                "--mechanic-id",
                ns.mechanic_id,
                "--offset",
                str(ns.offset),
                "--limit",
                str(ns.limit),
                "--beats",
                str(ns.beats),
            ]
        else:
            if not 1 <= len(ns.when) <= 3:
                raise BridgeError("Supply one to three --when predicates")
            for predicate in ns.when:
                if len(predicate) > 350 or "\x00" in predicate:
                    raise BridgeError("Invalid --when predicate")
                result += ["--when", predicate]
            result += ["--min-posts", str(ns.min_posts), "--max-accounts", str(ns.max_accounts)]
        return result
    try:
        ZoneInfo(ns.timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise BridgeError("Unknown --timezone; use an IANA timezone such as UTC.") from exc
    operators = confined(root, ns.operators)
    if operators.suffix != ".toml" or operators.relative_to(root).parts[0] != "config":
        raise BridgeError("--operators must be a TOML registry inside config/.")
    result = [command, "--operators", str(operators), "--timezone", ns.timezone]
    if command == "intelligence-build":
        _table(root, DEFAULT_MASTER)
        if not ns.execute:
            result += ["--dry-run"]
        else:
            if not ns.approve_write:
                raise BridgeError(
                    "Build writes require --execute --approve-write after explicit user confirmation. First run the default dry-run."
                )
            _write_preflight(root)
        result += ["--json", "--workspace-out", DEFAULT_WORKSPACE, "--profile", ns.profile]
        if ns.profile == "evidence-only" and ns.through_stage not in (None, "timeline"):
            raise BridgeError("evidence-only stops at timeline; incompatible --through-stage")
        if ns.through_stage:
            result += ["--through-stage", ns.through_stage]
    else:
        if not ns.approve_write:
            raise BridgeError(
                "quality-audit writes a report: obtain user confirmation then pass --approve-write."
            )
        _write_preflight(root)
        result += ["--workspace", DEFAULT_WORKSPACE]
    return result


def bounded_integer(minimum: int, maximum: int) -> Any:
    def parse(value: str) -> int:
        number = int(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"Must be between {minimum} and {maximum}.")
        return number

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--root", required=True, help="Existing evidence workspace, never inferred from cwd."
    )
    parser.add_argument(
        "--python", default=sys.executable, help="Python with the separately installed 1.x engine."
    )
    parser.add_argument("--timeout", type=bounded_integer(1, 3600), default=120)
    parser.add_argument(
        "--max-output-bytes", type=bounded_integer(1024, MAX_OUTPUT_BYTES), default=MAX_OUTPUT_BYTES
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", allow_abbrev=False)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--master", default=DEFAULT_MASTER)
    query = commands.add_parser("query", allow_abbrev=False)
    query.add_argument("table")
    query.add_argument("--where", action="append", default=[])
    query.add_argument("--columns")
    query.add_argument("--limit", type=bounded_integer(1, 100), default=20)
    rank = commands.add_parser("rank-posts", allow_abbrev=False)
    rank.add_argument("--master", default=DEFAULT_MASTER)
    rank.add_argument(
        "--rank", choices=("relative", "breakout", "saves", "balanced"), default="relative"
    )
    rank.add_argument("--content-type", choices=("all", "slideshow", "video"), default="all")
    rank.add_argument("--top", type=bounded_integer(1, 100), default=20)
    compare = commands.add_parser("compare-cohorts", allow_abbrev=False)
    compare.add_argument("--group-by", required=True)
    compare.add_argument("--metric", default="views_vs_account_median")
    compare.add_argument("--operator-id")
    compare.add_argument("--account-id")
    compare.add_argument("--content-type", choices=("all", "slideshow", "video"), default="all")
    compare.add_argument("--family-id")
    compare.add_argument("--since", help="Inclusive UTC YYYY-MM-DD")
    compare.add_argument("--until", help="Inclusive UTC YYYY-MM-DD")
    compare.add_argument("--values", help="Explicit comma-separated cohort values")
    compare.add_argument("--max-groups", type=bounded_integer(1, 30), default=10)
    compare.add_argument("--examples", type=bounded_integer(0, 3), default=2)
    family = commands.add_parser("trace-family", allow_abbrev=False)
    family.add_argument("--family-id", required=True)
    family.add_argument("--operator-id")
    family.add_argument("--offset", type=bounded_integer(0, 1000000), default=0)
    family.add_argument("--limit", type=bounded_integer(1, 100), default=20)
    family.add_argument("--beats", type=bounded_integer(0, 10), default=3)
    for name in ("mechanic-groups", "trace-mechanic", "verify-pattern"):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("--metric", default="views_vs_account_median")
        command.add_argument("--content-type", choices=("all", "slideshow", "video"), default="all")
        command.add_argument("--operator-id")
        command.add_argument("--account-id")
        if name != "verify-pattern":
            command.add_argument("--axes", default="hook_technique,content_format,cta_type")
        if name == "mechanic-groups":
            command.add_argument("--min-posts", type=bounded_integer(2, 10000), default=3)
            command.add_argument("--max-groups", type=bounded_integer(1, 30), default=12)
            command.add_argument("--examples", type=bounded_integer(0, 3), default=2)
        elif name == "trace-mechanic":
            command.add_argument("--mechanic-id", required=True)
            command.add_argument("--offset", type=bounded_integer(0, 1000000), default=0)
            command.add_argument("--limit", type=bounded_integer(1, 50), default=15)
            command.add_argument("--beats", type=bounded_integer(0, 5), default=2)
        else:
            command.add_argument("--when", action="append", required=True)
            command.add_argument("--min-posts", type=bounded_integer(3, 10000), default=5)
            command.add_argument("--max-accounts", type=bounded_integer(1, 30), default=12)
    trace_strategy = commands.add_parser("trace-strategy", allow_abbrev=False)
    trace_strategy.add_argument("--hypothesis-id", required=True)
    trace_strategy.add_argument("--offset", type=bounded_integer(0, 1000000), default=0)
    trace_strategy.add_argument("--limit", type=bounded_integer(1, 50), default=20)
    trace_strategy.add_argument("--max-patterns", type=bounded_integer(1, 30), default=15)
    for name in ("intelligence-build", "quality-audit"):
        sub = commands.add_parser(name, allow_abbrev=False)
        sub.add_argument("--operators", default="config/operators.toml")
        sub.add_argument("--timezone", default="UTC")
        sub.add_argument(
            "--approve-write",
            action="store_true",
            help="Records user-authorized writes, not blanket authorization.",
        )
        if name == "intelligence-build":
            sub.add_argument("--profile", choices=("full", "evidence-only"), default="full")
            sub.add_argument(
                "--execute",
                action="store_true",
                help="Execute the offline build; default is read-only planning.",
            )
            sub.add_argument("--through-stage", choices=STAGES)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    try:
        root = workspace_root(ns.root)
        arguments = command_arguments(ns, root)
        python = engine_python(ns.python)
        dependency = preflight(python)
        entrypoint = ["-m", "creative_research"]
        if ns.command in {"query", "rank-posts"}:
            # Display-only round-trip precision; the unchanged CLI still calculates/filters.
            entrypoint = [
                "-c",
                "import pandas as pd, runpy; "
                "pd.set_option('display.float_format', lambda value: format(value, '.17g')); "
                "runpy.run_module('creative_research', run_name='__main__')",
            ]
        # Research queries use fixed canonical tables, aggregate the full matching
        # population and page only examples. Keep the same sanitized subprocess,
        # timeout and output budget as the existing offline bridge.
        if ns.command in {"compare-cohorts", "trace-family"}:
            research_script = Path(__file__).with_name("research_queries.py")
            argv = [python, "-I", str(research_script), "--root", str(root), *arguments]
        elif ns.command in {
            "mechanic-groups",
            "trace-mechanic",
            "verify-pattern",
            "trace-strategy",
        }:
            investigation_script = Path(__file__).with_name("creative_intelligence.py")
            argv = [python, "-I", str(investigation_script), "--root", str(root), *arguments]
        else:
            argv = [python, "-I", *entrypoint, "--root", str(root), "--color", "never", *arguments]
        result = run_process(argv, timeout=ns.timeout, max_bytes=ns.max_output_bytes)
        result.update(
            command=ns.command,
            root=str(root),
            engine_version=dependency["stdout"].strip(),
            untrusted_output=True,
        )
        print(json.dumps(result, ensure_ascii=False))
        return int(result["exit_code"])
    except (BridgeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "exit_code": 2,
                    "error": redact(str(exc)),
                    "hint": "Run scripts/doctor.py --python /path/to/engine-python; check --help.",
                }
            )
        )
        return 2
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "exit_code": 130,
                    "error": "Interrupted; completed generated outputs are retained.",
                }
            )
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
