from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from creative_research.pathing import project_root, resolve_path

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv")


def _first_existing(directory: Path, stems: tuple[str, ...], exts: tuple[str, ...]) -> Path | None:
    if not directory.exists():
        return None
    for stem in stems:
        for ext in exts:
            candidate = directory / f"{stem}{ext}"
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def _thumbnail_source(record: dict[str, Any]) -> Path | None:
    account = str(record.get("account") or "").strip()
    post_id = str(record.get("post_id") or "").strip()
    if not account or not post_id:
        return None

    archive = project_root() / "data/02_media/tiktok" / account / post_id
    cover = _first_existing(archive, ("cover",), IMAGE_EXTS)
    if cover:
        return cover

    for pattern in ("slide_001.*", "slide_01.*", "slide_1.*"):
        matches = sorted(
            p for p in archive.glob(pattern)
            if p.suffix.lower() in IMAGE_EXTS
        )
        if matches:
            return matches[0]
    return None


def _video_source(record: dict[str, Any]) -> Path | None:
    if str(record.get("content_type") or "") != "video":
        return None

    value = record.get("source_media_path")
    directory = resolve_path(str(value)) if value else None
    if directory and directory.exists():
        if directory.is_file() and directory.suffix.lower() in VIDEO_EXTS:
            return directory
        if directory.is_dir():
            candidates = sorted(
                p for p in directory.iterdir()
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS
            )
            if candidates:
                return max(candidates, key=lambda p: p.stat().st_size)

    account = str(record.get("account") or "").strip()
    post_id = str(record.get("post_id") or "").strip()
    if not account or not post_id:
        return None

    fallback = project_root() / "data/03_video_media" / account / post_id
    if not fallback.exists():
        return None
    candidates = sorted(
        p for p in fallback.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


def export_media_for_post(
    record: dict[str, Any],
    post_key: str,
    out_dir: Path,
    *,
    mode: str,
) -> dict[str, str]:
    if mode == "none":
        return {}

    slug = post_key.lower().replace(" ", "-")
    assets: dict[str, str] = {}

    thumb = _thumbnail_source(record)
    if thumb:
        thumb_dir = out_dir / "assets" / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        target = thumb_dir / f"{slug}{thumb.suffix.lower()}"
        shutil.copy2(thumb, target)
        assets["thumbnail_path"] = target.relative_to(out_dir).as_posix()

    if mode == "previews":
        video = _video_source(record)
        if video:
            video_dir = out_dir / "assets" / "videos"
            video_dir.mkdir(parents=True, exist_ok=True)
            target = video_dir / f"{slug}{video.suffix.lower()}"
            shutil.copy2(video, target)
            assets["video_path"] = target.relative_to(out_dir).as_posix()

    return assets


def select_media_keys(
    records: list[dict[str, Any]],
    *,
    limit: int,
) -> set[tuple[str, str]]:
    if limit <= 0 or limit >= len(records):
        return {
            (str(r.get("account") or ""), str(r.get("post_id") or ""))
            for r in records
        }

    def score(record: dict[str, Any]) -> tuple[float, float]:
        global_pct = record.get("global_views_pct")
        views = record.get("views")
        try:
            p = float(global_pct)
        except (TypeError, ValueError):
            p = -1.0
        try:
            v = float(views)
        except (TypeError, ValueError):
            v = -1.0
        return p, v

    ranked = sorted(records, key=score, reverse=True)[:limit]
    return {
        (str(r.get("account") or ""), str(r.get("post_id") or ""))
        for r in ranked
    }
