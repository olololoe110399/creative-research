"""Generate command discovery; validate examples without executing workflows."""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
from pathlib import Path
from unittest.mock import patch

from creative_research.cli import app as cli
from creative_research.cli.registry import COMMAND_SPECS
from creative_research.infrastructure.storage import write_text


def render() -> str:
    lines = [
        "# Command catalog",
        "",
        "Generated from `cli/registry.py`; run `make docs-check` to detect drift.",
        "Use `creative-research <command> --help` for options and required inputs.",
        "",
    ]
    for group in dict.fromkeys(spec.group for spec in COMMAND_SPECS):
        lines.extend([f"## {group}", ""])
        for spec in COMMAND_SPECS:
            if spec.group == group:
                lines.append(f"- `{spec.name}`: {spec.description}.")
        lines.append("")
    return "\n".join(lines)


def validate_docs(root: Path) -> tuple[int, int]:
    """Check local links and parse shell examples without executing command bodies."""

    class Parsed(BaseException):
        pass

    original = argparse.ArgumentParser.parse_args

    def parse_only(parser, args=None, namespace=None):
        original(parser, args, namespace)
        raise Parsed

    links = examples = 0
    paths = list(root.glob("*.md")) + list((root / "docs").rglob("*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            target = target.strip("<>").split("#", 1)[0]
            if not target or re.match(r"[a-z][a-z0-9+.-]*:", target):
                continue
            if not (path.parent / target).exists():
                raise ValueError(f"Broken documentation link: {path.name}: {target}")
            links += 1
        for block in re.findall(r"```(?:sh|bash)\n(.*?)```", text, re.DOTALL):
            for line in block.replace("\\\n", " ").splitlines():
                tokens = shlex.split(line, comments=True)
                if "creative-research" not in tokens:
                    continue
                args = tokens[tokens.index("creative-research") + 1 :]
                for index, token in enumerate(args):
                    if token.startswith((">", "2>")):
                        args = args[:index]
                        break
                _, rest = cli._global_parser().parse_known_args(args)
                if not rest or rest[0] in {"--help", "-h"}:
                    continue
                if rest[0] not in {spec.name for spec in COMMAND_SPECS}:
                    raise ValueError(f"Unknown documented command: {path.name}: {rest[0]}")
                with (
                    patch.object(argparse.ArgumentParser, "parse_args", parse_only),
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    try:
                        cli._dispatch(rest)
                    except Parsed:
                        pass
                    except SystemExit as error:
                        if error.code not in {None, 0}:
                            raise ValueError(f"Invalid CLI example: {path.name}: {line}") from error
                    else:
                        raise ValueError(f"CLI example did not reach a parser: {path.name}: {line}")
                examples += 1
    return links, examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "docs/commands.md"
    expected = render()
    if args.check:
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            parser.exit(
                1, "CLI catalog is stale. Run: uv run python scripts/generate_cli_docs.py\n"
            )
        print("CLI catalog: current")
        links, examples = validate_docs(path.parent.parent)
        print(f"Documentation: {links} local links and {examples} CLI examples validated")
    else:
        write_text(path, expected)
        print(f"Generated {path}")


if __name__ == "__main__":
    main()
