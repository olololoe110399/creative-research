"""Command-line adapter for analyze performance workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.analyze_performance as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive relative performance baselines from canonical posts. "
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
