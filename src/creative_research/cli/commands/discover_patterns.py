"""Command-line adapter for discover patterns workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.discover_patterns as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover deterministic evidence patterns from canonical analytics. "
            "No LLM call is performed."
        )
    )
    parser.add_argument("--analysis", default="data/05_master/creative_analysis.parquet")
    parser.add_argument("--performance", default="data/06_analytics/post_performance.parquet")
    parser.add_argument("--cadence", default="data/06_analytics/posting_cadence.parquet")
    parser.add_argument("--families", default="data/06_analytics/creative_families.parquet")
    parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    parser.add_argument(
        "--propagation",
        default="data/06_analytics/cross_account_propagation.parquet",
    )
    parser.add_argument(
        "--role-evidence",
        default="data/06_analytics/account_role_evidence.parquet",
    )
    parser.add_argument(
        "--strategy-changes",
        default="data/06_analytics/strategy_change_points.parquet",
    )
    parser.add_argument(
        "--strategy-members",
        default="data/06_analytics/strategy_window_members.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics")
    parser.add_argument("--min-sample", type=int, default=5)
    parser.add_argument("--min-performance-effect", type=float, default=0.10)
    parser.add_argument("--min-cadence-effect", type=float, default=0.25)
    parser.add_argument("--propagation-dominant-rate", type=float, default=0.70)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
