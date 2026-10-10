"""Command-line adapter for analyze propagation workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.analyze_propagation as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive cross-account creative-family propagation and descriptive account-role "
            "evidence. No scrape or LLM call is performed."
        )
    )
    parser.add_argument(
        "--members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--performance",
        default="data/06_analytics/post_performance.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
