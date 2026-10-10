"""Command-line adapter for promote knowledge workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.promote_knowledge as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Promote strategy hypotheses and creative families into a typed, "
            "evidence-linked knowledge bank. No LLM call is performed."
        )
    )
    parser.add_argument(
        "--hypotheses",
        default="data/06_analytics/strategy_hypotheses.parquet",
    )
    parser.add_argument(
        "--strategy-evidence",
        default="data/06_analytics/strategy_evidence_links.parquet",
    )
    parser.add_argument(
        "--families",
        default="data/06_analytics/creative_families.parquet",
    )
    parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    parser.add_argument(
        "--reviews",
        default=None,
        help="Optional local knowledge review TOML.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--out", default="data/07_knowledge")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
