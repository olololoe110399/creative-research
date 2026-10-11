"""Download image and video assets into one archive without interpreting content."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from creative_research.capture.cache import source_fingerprint
from creative_research.capture.media import MediaArchiveOptions, archive_media
from creative_research.capture.videos import VideoDownloadOptions, download_videos
from creative_research.infrastructure.locking import project_writer
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_jsonl, write_json, write_jsonl


@dataclass(frozen=True, slots=True)
class DownloadOptions:
    input: str
    out: str = "data/media"
    accounts: list[str] | None = None
    concurrency: int = 12
    timeout: float = 35.0
    retries: int = 1
    checkpoint_every: int = 100
    no_slides: bool = False
    no_covers: bool = False
    no_avatars: bool = False
    no_videos: bool = False
    cookies_from_browser: str | None = None
    cookies_file: str | None = None
    dry_run: bool = False


def run(options: DownloadOptions) -> dict[str, Any]:
    if options.dry_run:
        return _run(options)
    with project_writer():
        return _run(options)


def _run(options: DownloadOptions) -> dict[str, Any]:
    source = source_fingerprint(resolve_path(options.input))
    images = asyncio.run(
        archive_media(
            MediaArchiveOptions(
                input=options.input,
                out=options.out,
                accounts=options.accounts,
                concurrency=options.concurrency,
                timeout=options.timeout,
                retries=options.retries,
                checkpoint_every=options.checkpoint_every,
                no_slides=options.no_slides,
                no_covers=options.no_covers,
                no_avatars=options.no_avatars,
                dry_run=options.dry_run,
            )
        )
    )
    if options.dry_run:
        return {
            "dry_run": True,
            "images": images,
            "video_posts": images["video_posts"],
            "failed": 0,
        }
    out = resolve_path(options.out)
    videos: dict[str, Any] = {"failed": 0, "downloaded_or_cached": 0}
    if not options.no_videos:
        videos = download_videos(
            VideoDownloadOptions(
                input=options.out,
                out=options.out,
                cookies_from_browser=options.cookies_from_browser,
                cookies_file=options.cookies_file,
                post_keys=images["post_keys"],
            )
        )
    rows = read_jsonl(out / "media_manifest.jsonl")
    if not options.no_videos:
        rows.extend(
            dict(
                row,
                kind="video",
                path=row["video_path"],
                status="existing" if row["download_method"] == "cached" else "downloaded",
            )
            for row in read_jsonl(out / "video_manifest.jsonl")
        )
        rows.extend(dict(row, kind="video", status="failed") for row in videos.get("failures", []))
    write_jsonl(out / "media_manifest.jsonl", rows)
    result = {
        "dry_run": False,
        "images": images,
        "videos": videos,
        "failed": images["failed"] + videos["failed"],
        "source_fingerprint": source,
        "assets": {
            resolve_path(row["path"]).relative_to(out).as_posix(): {
                "sha256": row["sha256"],
                "bytes": row["bytes"],
                "source_fingerprint": row["source_fingerprint"],
            }
            for row in rows
            if row["status"] in {"downloaded", "existing"}
        },
    }
    if source_fingerprint(resolve_path(options.input)) != source:
        raise ValueError("Capture changed during download; resume from a stable snapshot")
    write_json(out / "download_report.json", result)
    return result
