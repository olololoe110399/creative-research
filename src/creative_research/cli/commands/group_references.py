"""Command-line adapter for group references workflow."""

from __future__ import annotations

import argparse

import creative_research.references.export as service
from creative_research.references.pack import (
    DEFAULT_GROUP_DIMENSIONS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create descriptive candidate groups from a reference pack."
    )
    parser.add_argument("references")
    parser.add_argument(
        "--dimensions",
        default=",".join(DEFAULT_GROUP_DIMENSIONS),
        help="Comma-separated grouping dimensions.",
    )
    parser.add_argument("--out", help="Default: candidate_groups.csv beside input.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.export_groups(**vars(args))


if __name__ == "__main__":
    main()
