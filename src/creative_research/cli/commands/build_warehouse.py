"""Command-line adapter for build warehouse workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.build_warehouse as service
from creative_research.constants import DEFAULT_MASTER_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill operator-aware canonical warehouse tables from an existing "
            "creative_master without scraping or rerunning Vision."
        )
    )
    parser.add_argument(
        "master",
        nargs="?",
        default=str(DEFAULT_MASTER_PATH),
        help="creative_master parquet/csv/jsonl",
    )
    parser.add_argument(
        "--operators",
        required=True,
        help="Verified operator registry TOML (for example config/operators.toml)",
    )
    parser.add_argument("--out", default="data/05_master")
    parser.add_argument(
        "--allow-unmapped",
        action="store_true",
        help="Keep unregistered accounts with operator_id=null instead of failing.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
