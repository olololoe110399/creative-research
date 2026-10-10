"""Command-line adapter for quality audit workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.quality_audit as service
from creative_research.pipeline.contracts import DEFAULT_WORKSPACE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit deterministic operator-intelligence outputs for coverage, duplicate IDs, "
            "referential integrity, evidence lineage, trust status, and workspace completeness."
        )
    )
    parser.add_argument("--root", default=None)
    parser.add_argument(
        "--operators",
        default="config/operators.toml",
        help="Operator registry used for freshness auditing.",
    )
    parser.add_argument(
        "--reviews",
        default=None,
        help="Optional knowledge review TOML used for freshness auditing.",
    )
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument(
        "--workspace",
        default=DEFAULT_WORKSPACE,
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Defaults to quality_report.json inside --workspace.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as failures.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        service.run(**vars(args))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
