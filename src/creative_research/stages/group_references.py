from __future__ import annotations

import argparse
from pathlib import Path

from creative_research.reference_pack import (
    DEFAULT_GROUP_DIMENSIONS,
    group_references,
    load_master,
    write_table,
)


def main() -> None:
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
    args = parser.parse_args()

    source_path, df = load_master(args.references)
    dimensions = [value.strip() for value in args.dimensions.split(",") if value.strip()]
    result = group_references(df, dimensions=dimensions)
    out = Path(args.out).expanduser().resolve() if args.out else source_path.with_name("candidate_groups.csv")
    write_table(result, out)
    print(out)


if __name__ == "__main__":
    main()
