"""Command-line adapter for analyze cadence workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.analyze_cadence as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive historical posting cadence at account and operator level. "
            "No scrape, realtime collection, or LLM call is performed."
        )
    )
    parser.add_argument(
        "posts",
        nargs="?",
        default="data/05_master/posts.parquet",
        help="Canonical posts parquet/csv/jsonl.",
    )
    parser.add_argument("--out", default="data/06_analytics")
    parser.add_argument(
        "--timezone",
        default="UTC",
        help="Timezone used for posting-hour/day analysis (for example Asia/Ho_Chi_Minh).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
