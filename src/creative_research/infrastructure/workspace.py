"""Read-only capture inventories and environment diagnostics."""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

from creative_research.constants import WORKSPACE_DIRS


def doctor_checks() -> list[tuple[str, bool, str, bool]]:
    checks: list[tuple[str, bool, str, bool]] = []
    for name in ("apify_client", "httpx", "yt_dlp"):
        present = importlib.util.find_spec(name) is not None
        checks.append((f"python:{name}", present, "ok" if present else "missing", True))
    binary = shutil.which("ffprobe")
    checks.append(("ffprobe", bool(binary), binary or "optional", False))
    present = bool(os.environ.get("APIFY_TOKEN"))
    checks.append(("env:APIFY_TOKEN", present, "set" if present else "not set", False))
    return checks


def initialize_workspace(root: Path) -> None:
    for directory in WORKSPACE_DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)


def status_rows(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, name in (
        ("crawl records", "data/raw"),
        ("media files", "data/media"),
        ("exports", "exports"),
        ("pipeline files", "data/runs"),
    ):
        directory = root / name
        count = sum(path.is_file() for path in directory.rglob("*")) if directory.is_dir() else None
        rows.append({"label": label, "path": name, "present": count is not None, "count": count})
    return rows
