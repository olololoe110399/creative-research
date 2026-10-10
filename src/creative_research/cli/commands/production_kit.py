"""Command-line adapter for production kit workflow."""

from __future__ import annotations

import argparse

import creative_research.production.export as service
from creative_research.production.kit import DEFAULT_DAYS, DEFAULT_RECIPES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export team-ready, evidence-linked recipe briefs, calendar, "
            "account launch guide and asset verification tasks. Offline."
        )
    )
    parser.add_argument(
        "--workspace",
        default="data/07_exports/operator-intelligence",
    )
    parser.add_argument("--recipes", type=int, default=DEFAULT_RECIPES)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument(
        "--raw-root",
        default=None,
        help="Optional local Apify/raw archive with observed captions and sound metadata.",
    )
    parser.add_argument(
        "--clearance-csv",
        default=None,
        help="Optional team rights-attestation CSV; must name real license evidence.",
    )
    parser.add_argument(
        "--own-results-csv",
        default=None,
        help="Optional actual first-party post metrics. Never claims operator causation.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
