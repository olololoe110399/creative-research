"""Command-line adapter for select accounts workflow."""

from __future__ import annotations

import argparse

import creative_research.capture.accounts as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge snapshots and keep selected TikTok accounts."
    )
    parser.add_argument("--sources", nargs="+", required=True)
    parser.add_argument("--accounts", nargs="+", required=True)
    parser.add_argument("--out", default="selected_accounts")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
