"""Copy the canonical skill into explicit project-scoped Claude Code/Codex discovery paths."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_NAME = "creative-research"
SOURCE = Path(__file__).resolve().parents[1] / "skills" / SKILL_NAME
TARGETS = {"claude": ".claude/skills", "codex": ".agents/skills"}


def install(source: Path, project: Path, targets: list[str]) -> list[Path]:
    """Preflight all destinations; refuse replacing existing work or following symlinks."""
    if not project.is_dir():
        raise ValueError("--project must be an existing directory.")
    if not (source / "SKILL.md").is_file() or source.is_symlink():
        raise ValueError("Canonical skill is missing or symlinked.")
    files = [path for path in source.rglob("*") if path.is_file()]
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Canonical skill must not contain symlinks.")
    files = [path for path in files if "__pycache__" not in path.parts and path.suffix != ".pyc"]
    if any(path.suffix not in {".md", ".py"} for path in files):
        raise ValueError("Unexpected canonical skill file; review before installation.")
    destinations = [project / TARGETS[name] / SKILL_NAME for name in targets]
    for destination in destinations:
        for parent in (destination, *destination.parents):
            if parent == project:
                break
            if parent.is_symlink():
                raise ValueError("Skill discovery paths must not be symlinked.")
        if destination.exists():
            raise ValueError(
                f"Already installed: {destination}. Preserve or move the old copy explicitly before reinstalling."
            )
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".skill-install-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / SKILL_NAME
            staged.mkdir()
            for path in files:
                target = staged / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            staged.rename(destination)
    return destinations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--project", required=True, help="Existing destination project; never a guessed home path."
    )
    parser.add_argument("--target", choices=(*TARGETS, "both"), required=True)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python containing the separately installed engine.",
    )
    ns = parser.parse_args(argv)
    try:
        doctor = subprocess.run(
            [sys.executable, str(SOURCE / "scripts/doctor.py"), "--python", ns.python],
            capture_output=True,
            text=True,
            timeout=40,
        )
        if doctor.returncode:
            raise ValueError(
                "Engine preflight failed. Run skills/creative-research/scripts/doctor.py with --python first. Nothing was installed."
            )
        targets = list(TARGETS) if ns.target == "both" else [ns.target]
        destinations = install(SOURCE, Path(ns.project).expanduser().resolve(), targets)
        print(
            json.dumps(
                {
                    "installed": [str(path) for path in destinations],
                    "dependencies": json.loads(doctor.stdout),
                }
            )
        )
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
