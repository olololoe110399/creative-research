"""Command-line adapter for table queries."""

from __future__ import annotations

import argparse

from creative_research.references.export import query_table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a normalized creative table without writing ad-hoc Pandas code."
    )
    parser.add_argument("table")
    parser.add_argument(
        "--where", action="append", default=[], help="Condition such as views>=10000."
    )
    parser.add_argument("--columns", help="Comma-separated output columns.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", help="Optional .csv, .parquet, or .jsonl output.")
    args = parser.parse_args()
    query_table(**vars(args))


if __name__ == "__main__":
    main()
