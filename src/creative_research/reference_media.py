from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from creative_research.pathing import project_root, resolve_path

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _first_url(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith(("http://", "https://")):
                return value
    return None


def _dedupe_urls(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        value = value.strip()
        if not value.startswith(("http://", "https://")) or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _archive_dir(record: dict[str, Any]) -> Path | None:
    account = str(record.get("account") or "").strip()
    post_id = str(record.get("post_id") or "").strip()
    if not account or not post_id:
        return None
    return project_root() / "data/02_media/tiktok" / account / post_id


def _source_documents(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    archive = _archive_dir(record)
    if not archive:
        return {}, {}
    return _read_json(archive / "meta.json"), _read_json(archive / "raw.json")


def _first_existing(
    directory: Path,
    stems: tuple[str, ...],
    exts: tuple[str, ...],
) -> Path | None:
    if not directory.exists():
        return None
    for stem in stems:
        for ext in exts:
            candidate = directory / f"{stem}{ext}"
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def _thumbnail_source(record: dict[str, Any]) -> Path | None:
    archive = _archive_dir(record)
    if not archive:
        return None

    cover = _first_existing(archive, ("cover",), IMAGE_EXTS)
    if cover:
        return cover

    for pattern in ("slide_001.*", "slide_01.*", "slide_1.*"):
        matches = sorted(
            p
            for p in archive.glob(pattern)
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
                p
                for p in directory.iterdir()
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
        p
        for p in fallback.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


def _direct_video_urls(obj: Any) -> list[str]:
    out: list[str] = []

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key).lower())
            return
        if isinstance(value, list):
            for child in value:
                walk(child, key)
            return
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return

        pathish = value.lower().split("?", 1)[0]
        if any(pathish.endswith(ext) for ext in IMAGE_EXTS):
            return

        key_ok = any(
            token in key
            for token in ("video", "play", "download", "playaddr", "downloadaddr")
        )
        url_ok = any(
            token in value.lower()
            for token in (
                ".mp4",
                "video/tos",
                "v16-webapp",
                "v19-webapp",
                "mime_type=video",
            )
        )
        if (key_ok or url_ok) and "tiktok.com/@" not in value.lower():
            out.append(value)

    walk(obj)
    return _dedupe_urls(out)


def _remote_media(record: dict[str, Any]) -> dict[str, Any]:
    meta, raw = _source_documents(record)
    video_meta = raw.get("videoMeta") or raw.get("video") or {}
    if not isinstance(video_meta, dict):
        video_meta = {}

    post_url = _first_url(
        record.get("url"),
        meta.get("url"),
        raw.get("webVideoUrl"),
        raw.get("url"),
    )

    slide_urls: list[str] = []
    for item in raw.get("slideshowImageLinks") or []:
        if not isinstance(item, dict):
            continue
        url = _first_url(item.get("tiktokLink"), item.get("downloadLink"))
        if url:
            slide_urls.append(url)
    slide_urls = _dedupe_urls(slide_urls)

    thumbnail_url = _first_url(
        slide_urls[0] if slide_urls else None,
        video_meta.get("originalCoverUrl"),
        meta.get("cover_original_url"),
        video_meta.get("coverUrl"),
        meta.get("cover_apify_url"),
    )

    result: dict[str, Any] = {}
    if post_url:
        result["post_url"] = post_url
    if thumbnail_url:
        result["thumbnail_url"] = thumbnail_url
    if slide_urls:
        result["slide_urls"] = slide_urls

    if str(record.get("content_type") or "") == "video":
        video_urls = _direct_video_urls(raw)
        if video_urls:
            result["video_url"] = video_urls[0]
            if len(video_urls) > 1:
                result["video_fallback_urls"] = video_urls[1:4]

    return result


def _copy_local_assets(
    record: dict[str, Any],
    post_key: str,
    out_dir: Path,
    *,
    include_video: bool,
) -> dict[str, str]:
    slug = post_key.lower().replace(" ", "-")
    assets: dict[str, str] = {}

    thumb = _thumbnail_source(record)
    if thumb:
        thumb_dir = out_dir / "assets" / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        target = thumb_dir / f"{slug}{thumb.suffix.lower()}"
        shutil.copy2(thumb, target)
        assets["thumbnail_path"] = target.relative_to(out_dir).as_posix()

    if include_video:
        video = _video_source(record)
        if video:
            video_dir = out_dir / "assets" / "videos"
            video_dir.mkdir(parents=True, exist_ok=True)
            target = video_dir / f"{slug}{video.suffix.lower()}"
            shutil.copy2(video, target)
            assets["video_path"] = target.relative_to(out_dir).as_posix()

    return assets


def preview_media_for_post(record: dict[str, Any]) -> dict[str, str]:
    """Return lightweight remote preview media for full-population browsing."""
    media = _remote_media(record)
    result: dict[str, str] = {}
    post_url = media.get("post_url")
    thumbnail_url = media.get("thumbnail_url")
    if isinstance(post_url, str) and post_url:
        result["post_url"] = post_url
    if isinstance(thumbnail_url, str) and thumbnail_url:
        result["thumbnail_url"] = thumbnail_url
    return result


def export_media_for_post(
    record: dict[str, Any],
    post_key: str,
    out_dir: Path,
    *,
    mode: str,
) -> dict[str, Any]:
    if mode == "none":
        return {}

    if mode == "remote":
        return _remote_media(record)

    if mode == "copy":
        result = _remote_media(record)
        result.pop("thumbnail_url", None)
        result.pop("slide_urls", None)
        result.pop("video_url", None)
        result.pop("video_fallback_urls", None)
        result.update(
            _copy_local_assets(
                record,
                post_key,
                out_dir,
                include_video=True,
            )
        )
        return result

    if mode == "hybrid":
        result = _remote_media(record)
        result.update(
            _copy_local_assets(
                record,
                post_key,
                out_dir,
                include_video=True,
            )
        )
        return result

    raise ValueError(f"Unsupported media mode: {mode}")


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
