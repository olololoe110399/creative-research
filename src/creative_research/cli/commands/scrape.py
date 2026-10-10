"""Command-line adapter for scrape workflow."""

from __future__ import annotations

import argparse

import creative_research.capture.scrape as service


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Archive public TikTok profile posts via Apify.")

    p.add_argument(
        "accounts_file",
        help="Text file: one TikTok username or profile URL per line",
    )
    p.add_argument(
        "--out",
        default="tiktok_snapshot",
        help="Output directory",
    )
    p.add_argument(
        "--token",
        default=None,
        help="Apify token. Prefer APIFY_TOKEN env var instead.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Profiles per Actor run. Default: 4",
    )
    p.add_argument(
        "--max-posts",
        type=int,
        default=10000,
        help="Max posts requested per profile. Default: 10000",
    )
    p.add_argument(
        "--actor-timeout",
        type=int,
        default=7200,
        help="Max Actor runtime per batch in seconds. Default: 7200",
    )
    p.add_argument(
        "--max-charge-usd",
        type=float,
        default=None,
        help="Optional USD charge cap applied to EACH Actor batch.",
    )

    p.add_argument(
        "--download-videos",
        action="store_true",
        help="Download videos into Apify KVS, then mirror locally",
    )

    p.set_defaults(download_covers=True)
    p.add_argument(
        "--no-covers",
        dest="download_covers",
        action="store_false",
        help="Do not download cover images",
    )

    p.set_defaults(download_slides=True)
    p.add_argument(
        "--no-slides",
        dest="download_slides",
        action="store_false",
        help="Do not download slideshow images",
    )

    p.set_defaults(download_avatars=True)
    p.add_argument(
        "--no-avatars",
        dest="download_avatars",
        action="store_false",
        help="Do not download profile avatars",
    )

    p.add_argument(
        "--subtitles",
        choices=[
            "NEVER_DOWNLOAD_SUBTITLES",
            "DOWNLOAD_SUBTITLES",
            "DOWNLOAD_AND_TRANSCRIBE_VIDEOS_WITHOUT_SUBTITLES",
            "TRANSCRIBE_ALL_VIDEOS",
        ],
        default="NEVER_DOWNLOAD_SUBTITLES",
        help="Default: NEVER_DOWNLOAD_SUBTITLES",
    )

    p.add_argument(
        "--comments",
        type=int,
        default=0,
        help="Maximum comments per post. Default 0.",
    )
    p.add_argument(
        "--top-level-comments",
        type=int,
        default=0,
        help="Maximum top-level comments per post. Default 0.",
    )
    p.add_argument(
        "--max-replies",
        type=int,
        default=0,
        help="Maximum replies per comment. Default 0.",
    )

    p.add_argument(
        "--oldest-date",
        default=None,
        help="Optional Actor date filter; may add cost.",
    )
    p.add_argument(
        "--newest-date",
        default=None,
        help="Optional Actor date filter; may add cost.",
    )

    p.add_argument(
        "--skip-media-sync",
        action="store_true",
        help="Keep media in Apify KVS but do not mirror it locally.",
    )

    p.add_argument(
        "--operators",
        default="config/operators.toml",
        help="Researcher-confirmed operator registry; mandatory before paid scrape.",
    )
    p.add_argument(
        "--operator-id",
        default=None,
        help="Optional expected operator ID; reject accounts assigned elsewhere.",
    )
    p.add_argument(
        "--preflight",
        action="store_true",
        help="Validate account grouping without token, network, or charges.",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    service.archive_posts(service.ScrapeOptions(**vars(args)))


if __name__ == "__main__":
    main()
