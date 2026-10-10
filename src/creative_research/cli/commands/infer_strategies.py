"""Command-line adapter for infer strategies workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.infer_strategies as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Promote deterministic evidence patterns into reviewable strategy hypotheses "
            "with supporting/counter evidence. No LLM call is performed."
        )
    )
    parser.add_argument("--patterns", default="data/06_analytics/patterns.parquet")
    parser.add_argument(
        "--pattern-evidence",
        default="data/06_analytics/pattern_evidence_links.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
