"""Command-line adapter for build families workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.build_families as service
from creative_research.analysis.build_families import (
    DEFAULT_BRIDGE_FLOOR,
    DEFAULT_THRESHOLD,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build production creative families from canonical posts, Vision evidence, "
            "and optional cached AI pair judgments. This stage never makes an LLM call."
        )
    )
    parser.add_argument(
        "--posts",
        default="data/05_master/posts.parquet",
    )
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--sequence",
        default="data/05_master/creative_sequence.parquet",
    )
    parser.add_argument(
        "--performance",
        default="data/06_analytics/post_performance.parquet",
        help="Optional performance analytics used only for family summaries/representative choice.",
    )
    parser.add_argument("--out", default="data/06_analytics")
    parser.add_argument(
        "--family-model",
        choices=("v1", "v2"),
        default="v2",
        help="Production family model. v2 is calibrated hybrid core-family clustering; v1 is the legacy deterministic model.",
    )
    parser.add_argument(
        "--ai-judgments",
        default="data/06_analytics/family_ai/family_ai_judgments.parquet",
        help="Optional precomputed AI pair judgments. Missing file is allowed and never triggers an API call.",
    )
    parser.add_argument(
        "--calibration-max-pairs",
        type=int,
        default=50_000,
        help="Maximum retained deterministic calibration pairs for family v2.",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--bridge-floor", type=float, default=DEFAULT_BRIDGE_FLOOR)
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print clustering progress every N posts; use 0 to disable.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
