"""Command-line adapter for download videos workflow."""

from __future__ import annotations

import argparse

import creative_research.capture.videos as service


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="creative_videos")
    ap.add_argument("--cookies-from-browser", default=None)
    ap.add_argument("--cookies-file", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-direct-fallback", action="store_true")
    return ap


def main() -> None:
    args = build_parser().parse_args()
    service.download_videos(service.VideoDownloadOptions(**vars(args)))


if __name__ == "__main__":
    main()
