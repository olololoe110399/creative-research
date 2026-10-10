"""Command-line adapter for preview families v2 workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.preview_families_v2 as service
from creative_research.analysis.preview_families_v2 import (
    DEFAULT_BRIDGE_COMBINED,
    DEFAULT_MIN_AI_CONFIDENCE,
    DEFAULT_STRONG_COMBINED,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview a conservative creative-family v2 clustering model from "
            "family calibration pair evidence without overwriting production families."
        )
    )
    parser.add_argument("--posts", default="data/05_master/posts.parquet")
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--pairs",
        default=("data/06_analytics/family_calibration/family_calibration_pairs.parquet"),
    )
    parser.add_argument(
        "--out",
        default="data/06_analytics/family_v2_preview",
    )
    parser.add_argument(
        "--ai-judgments",
        default="data/06_analytics/family_ai/family_ai_judgments.parquet",
        help="Optional AI pair judgments; missing file falls back to deterministic gates.",
    )
    parser.add_argument(
        "--min-ai-confidence",
        type=float,
        default=DEFAULT_MIN_AI_CONFIDENCE,
    )
    parser.add_argument(
        "--strong-combined",
        type=float,
        default=DEFAULT_STRONG_COMBINED,
    )
    parser.add_argument(
        "--bridge-combined",
        type=float,
        default=DEFAULT_BRIDGE_COMBINED,
    )
    parser.add_argument("--review-limit", type=int, default=150)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
