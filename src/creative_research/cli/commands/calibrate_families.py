"""Command-line adapter for calibrate families workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.calibrate_families as service
from creative_research.analysis.calibrate_families import (
    DEFAULT_MAX_PAIRS,
    DEFAULT_MIN_COMBINED,
    DEFAULT_MIN_STRUCTURE,
    DEFAULT_PROGRESS_EVERY,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure language-independent structure similarity and Vision-text similarity "
            "to calibrate creative-family discovery without changing production families."
        )
    )
    parser.add_argument("--posts", default="data/05_master/posts.parquet")
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--sequence",
        default="data/05_master/creative_sequence.parquet",
    )
    parser.add_argument(
        "--members",
        default="data/06_analytics/creative_family_members.parquet",
        help="Optional current family membership for split-vs-grouped diagnostics.",
    )
    parser.add_argument(
        "--out",
        default="data/06_analytics/family_calibration",
    )
    parser.add_argument(
        "--min-structure",
        type=float,
        default=DEFAULT_MIN_STRUCTURE,
    )
    parser.add_argument(
        "--min-combined",
        type=float,
        default=DEFAULT_MIN_COMBINED,
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=DEFAULT_MAX_PAIRS,
    )
    parser.add_argument(
        "--review-per-bucket",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
        help="Print progress every N blocked candidate pairs; use 0 to disable.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
