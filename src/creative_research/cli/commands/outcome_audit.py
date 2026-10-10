"""Command-line adapter for outcome audit workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.outcome_audit as service
from creative_research.pipeline.contracts import DEFAULT_WORKSPACE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit evidence-to-decision contracts in a materialized Lab."
    )
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero until trusted knowledge is ready for usability testing.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
