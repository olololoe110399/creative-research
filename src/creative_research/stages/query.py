from __future__ import annotations

import argparse
from pathlib import Path

from creative_research.reference_pack import apply_conditions, load_master, write_table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a normalized creative table without writing ad-hoc Pandas code."
    )
    parser.add_argument("table")
    parser.add_argument("--where", action="append", default=[], help="Condition such as views>=10000.")
    parser.add_argument("--columns", help="Comma-separated output columns.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", help="Optional .csv, .parquet, or .jsonl output.")
    args = parser.parse_args()

    _, df = load_master(args.table)
    result = apply_conditions(df, args.where)
    if args.columns:
        columns = [value.strip() for value in args.columns.split(",") if value.strip()]
        missing = [name for name in columns if name not in result.columns]
        if missing:
            raise SystemExit("Unknown output columns: " + ", ".join(missing))
        result = result[columns]
    if args.limit is not None:
        result = result.head(args.limit)

    if args.out:
        path = Path(args.out).expanduser().resolve()
        write_table(result, path)
        print(path)
    else:
        print(result.to_string(index=False))


if __name__ == "__main__":
    main()
