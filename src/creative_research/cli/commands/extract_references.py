"""Command-line adapter for extract references workflow."""

from __future__ import annotations

import argparse

import creative_research.references.export as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a portable ranked creative reference pack from creative_master."
    )
    parser.add_argument("master")
    parser.add_argument("--out", default="data/07_exports/reference-pack")
    parser.add_argument(
        "--rank", choices=["relative", "breakout", "saves", "balanced"], default="relative"
    )
    parser.add_argument(
        "--content-type", choices=["all", "slideshow", "video"], default="slideshow"
    )
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument(
        "--strategy",
        choices=["system", "account-balanced", "top"],
        default="system",
        help=(
            "Reference sampling strategy. system covers accounts first, then "
            "balances performance and structural diversity. Default: system."
        ),
    )
    parser.add_argument(
        "--media",
        choices=["none", "remote", "copy", "hybrid"],
        default="remote",
        help="Media for the Reference Workspace. Default: remote.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.export_references(**vars(args))


if __name__ == "__main__":
    main()
