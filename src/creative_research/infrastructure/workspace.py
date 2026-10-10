"""Workspace diagnostics, evidence adoption and filesystem inventories."""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from creative_research.constants import WORKSPACE_DIRS


def _check_import(name: str) -> tuple[bool, str]:
    try:
        spec = importlib.util.find_spec(name)
        return (spec is not None, "ok" if spec is not None else "missing")
    except (ImportError, ValueError) as exc:
        return False, f"error: {exc}"


def doctor_checks() -> list[tuple[str, bool, str, bool]]:
    """Return checks as (name, ok, detail, required)."""
    checks: list[tuple[str, bool, str, bool]] = []

    uv = shutil.which("uv")
    checks.append(("uv", bool(uv), uv or "not found", True))

    ffprobe = shutil.which("ffprobe")
    checks.append(("ffprobe", bool(ffprobe), ffprobe or "not found", False))

    ytdlp_bin = shutil.which("yt-dlp")
    ytdlp_mod, _ = _check_import("yt_dlp")
    checks.append(
        (
            "yt-dlp",
            bool(ytdlp_bin or ytdlp_mod),
            ytdlp_bin or ("python module" if ytdlp_mod else "not found"),
            True,
        )
    )

    for mod in ["apify_client", "httpx", "pandas", "pyarrow", "google.genai", "pydantic"]:
        ok, detail = _check_import(mod)
        checks.append((f"python:{mod}", ok, detail, True))

    for env_name in ["APIFY_TOKEN", "GEMINI_API_KEY"]:
        present = bool(os.environ.get(env_name))
        checks.append((f"env:{env_name}", present, "set" if present else "not set", False))

    return checks


def _validate_adoption(source: Path, dest: Path, replace: bool) -> None:
    if not source.exists():
        raise ValueError(f"Source does not exist: {source}")
    resolved_dest = dest.resolve()
    if (
        source == resolved_dest
        or source.is_relative_to(resolved_dest)
        or resolved_dest.is_relative_to(source)
    ):
        raise ValueError(f"Adoption source and destination overlap: {source} -> {dest}")
    if (dest.exists() or dest.is_symlink()) and not replace:
        raise ValueError(
            f"Destination already exists: {dest}. Use --replace to keep a backup and replace it."
        )


def adopt_artifact(src: str | None, dest: Path, mode: str, replace: bool) -> None:
    if not src:
        return
    from creative_research.infrastructure.paths import resolve_path

    source = resolve_path(src)
    _validate_adoption(source, dest, replace)
    if mode not in {"symlink", "copy"}:
        raise ValueError(f"Unsupported adopt mode: {mode}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".adopt-", dir=dest.parent) as temporary:
        staged = Path(temporary) / "artifact"
        if mode == "symlink":
            staged.symlink_to(source, target_is_directory=source.is_dir())
        elif source.is_dir():
            shutil.copytree(source, staged)
        else:
            shutil.copy2(source, staged)
        backup = None
        if dest.exists() or dest.is_symlink():
            backup = dest.with_name(f"{dest.name}.backup-{uuid4().hex[:12]}")
            dest.replace(backup)
        try:
            staged.replace(dest)
        except OSError:
            if backup is not None and not dest.exists() and not dest.is_symlink():
                backup.replace(dest)
            raise
        if backup is not None:
            print(f"Previous output retained at: {backup}")
    print(f"{mode}: {dest} -> {source}")


def _count_lines(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            return sum(1 for line in f if line.strip())
    except (OSError, UnicodeError) as exc:
        logging.getLogger(__name__).warning(
            "workspace_input_unreadable",
            extra={"context": {"path": str(path), "error_type": type(exc).__name__}},
        )
        return None


def _count_media_posts(root: Path) -> int | None:
    if not root.exists():
        return None
    total = 0
    for account in root.iterdir():
        if not account.is_dir():
            continue
        for post in account.iterdir():
            if (
                post.is_dir()
                and post.name != "profile"
                and ((post / "meta.json").exists() or (post / "raw.json").exists())
            ):
                total += 1
    return total


def status_rows(root: Path) -> list[dict[str, object]]:
    candidates = [
        (
            "selected normalized posts",
            root / "data/01_selected/targets/normalized/posts.jsonl",
            "lines",
        ),
        ("local media posts", root / "data/02_media/tiktok", "media"),
        ("slideshow manifest", root / "data/03_manifests/slides/full_manifest.jsonl", "lines"),
        ("video manifest", root / "data/03_video_media/video_manifest.jsonl", "lines"),
        (
            "slideshow vision results",
            root / "data/04_vision/slides/creative_study_v2.jsonl",
            "lines",
        ),
        (
            "video vision results",
            root / "data/04_vision/videos/creative_video_study.jsonl",
            "lines",
        ),
        ("creative master", root / "data/05_master/creative_master.jsonl", "lines"),
        ("post performance", root / "data/06_analytics/post_performance.parquet", "file"),
        ("posting cadence", root / "data/06_analytics/posting_cadence.parquet", "file"),
        ("creative families", root / "data/06_analytics/creative_families.parquet", "file"),
        (
            "cross-account propagation",
            root / "data/06_analytics/cross_account_propagation.parquet",
            "file",
        ),
        ("account role evidence", root / "data/06_analytics/account_role_evidence.parquet", "file"),
        ("strategy timeline", root / "data/06_analytics/strategy_windows.parquet", "file"),
        ("evidence patterns", root / "data/06_analytics/patterns.parquet", "file"),
        ("strategy hypotheses", root / "data/06_analytics/strategy_hypotheses.parquet", "file"),
        ("knowledge catalog", root / "data/07_knowledge/knowledge_catalog.parquet", "file"),
        (
            "intelligence workspace",
            root / "data/07_exports/operator-intelligence/workspace.json",
            "file",
        ),
        (
            "intelligence quality",
            root / "data/07_exports/operator-intelligence/quality_report.json",
            "file",
        ),
    ]
    rows: list[dict[str, object]] = []
    for label, path, kind in candidates:
        if kind == "lines":
            count = _count_lines(path)
        elif kind == "media":
            count = _count_media_posts(path)
        else:
            count = 1 if path.is_file() else None
        rows.append(
            {
                "label": label,
                "path": str(path.relative_to(root)),
                "present": count is not None,
                "count": count,
            }
        )
    return rows


def adopt_outputs(requests: list[tuple[str | None, Path]], *, mode: str, replace: bool) -> None:
    from creative_research.infrastructure.paths import resolve_path

    selected = [(source, dest) for source, dest in requests if source]
    if len({dest for _, dest in selected}) != len(selected):
        raise ValueError("Adoption destinations must be unique")
    for source, dest in selected:
        _validate_adoption(resolve_path(source), dest, replace)
    for source, dest in selected:
        adopt_artifact(source, dest, mode, replace)


def initialize_workspace(root: Path) -> None:
    for directory in WORKSPACE_DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)
