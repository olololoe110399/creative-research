"""Command-line adapter for operator setup workflow."""

from __future__ import annotations

import argparse

import creative_research.operating.onboarding as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Confirm operator/account grouping once before a paid scrape."
    )
    parser.add_argument("--accounts-file", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", default="config/operators.toml")
    parser.add_argument(
        "--confirm-same-operator",
        action="store_true",
        help="Explicitly assert all listed accounts belong to the same operator.",
    )
    parser.add_argument(
        "--replace", action="store_true", help="Explicitly replace an existing local registry."
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
