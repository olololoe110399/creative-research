"""Command-line adapter for analyze timeline workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.analyze_timeline as service
from creative_research.analysis.analyze_timeline import (
    FREQUENCIES,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic operator/account strategy timelines and adjacent-window "
            "change scores. No scrape or LLM call is performed."
        )
    )
    parser.add_argument("--posts", default="data/05_master/posts.parquet")
    parser.add_argument("--analysis", default="data/05_master/creative_analysis.parquet")
    parser.add_argument("--performance", default="data/06_analytics/post_performance.parquet")
    parser.add_argument("--cadence", default="data/06_analytics/posting_cadence.parquet")
    parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    parser.add_argument(
        "--family-entries",
        default="data/06_analytics/family_account_entries.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics")
    parser.add_argument("--frequency", choices=sorted(FREQUENCIES), default="month")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--min-posts", type=int, default=5)
    parser.add_argument("--change-threshold", type=float, default=0.24)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
