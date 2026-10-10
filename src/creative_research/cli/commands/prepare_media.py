"""Command-line adapter for prepare media workflow."""

from __future__ import annotations

import argparse
import asyncio

import creative_research.capture.media as service


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Organize/download TikTok slideshow/cover media. "
            "Prefer TikTok CDN and rotate Apify tokens only as fallback."
        )
    )

    p.add_argument(
        "input",
        help="Merged TikTok dataset folder containing posts/*.jsonl",
    )
    p.add_argument(
        "--out",
        default="tiktok_media",
        help="Output directory",
    )
    p.add_argument(
        "--accounts",
        nargs="*",
        help="Optional usernames; if omitted, process all accounts",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=12,
        help="Concurrent downloads. Default: 12",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=35.0,
        help="HTTP timeout seconds. Default: 35",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retries for transient 429/5xx/network errors. Default: 1",
    )
    p.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Save manifest every N attempted jobs. Default: 100",
    )
    p.add_argument(
        "--no-slides",
        action="store_true",
        help="Do not download slideshow images",
    )
    p.add_argument(
        "--no-covers",
        action="store_true",
        help="Do not download cover images",
    )
    p.add_argument(
        "--no-avatars",
        action="store_true",
        help="Do not download profile avatars",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build folders/manifests but do not download media",
    )

    return p


def main() -> None:
    args = build_parser().parse_args()
    options = service.MediaArchiveOptions(**vars(args))
    try:
        asyncio.run(service.archive_media(options))
    except KeyboardInterrupt:
        print("\nStopped by user. Existing files and last checkpoint are preserved.")


if __name__ == "__main__":
    main()
