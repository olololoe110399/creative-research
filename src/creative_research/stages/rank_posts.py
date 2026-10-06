from __future__ import annotations

import argparse
from pathlib import Path

from creative_research.reference_pack import load_master, rank_master, write_table

DISPLAY_COLUMNS = [
    "account",
    "post_id",
    "content_type",
    "views",
    "account_views_pct",
    "global_views_pct",
    "save_rate",
    "share_rate",
    "hook_text",
    "hook_technique",
    "content_angle",
    "content_format",
    "slide_count",
    "product_position",
    "cta_position",
    "url",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank creative_master posts for human review and reference selection."
    )
    parser.add_argument("master")
    parser.add_argument("--rank", choices=["relative", "breakout", "saves", "balanced"], default="relative")
    parser.add_argument("--content-type", choices=["all", "slideshow", "video"], default="all")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--out", help="Optional .csv, .parquet, or .jsonl output.")
    args = parser.parse_args()

    _, master = load_master(args.master)
    ranked = rank_master(master, rank=args.rank, content_type=args.content_type, top=args.top)
    if args.out:
        path = Path(args.out).expanduser().resolve()
        write_table(ranked, path)
        print(path)
        return

    columns = [name for name in DISPLAY_COLUMNS if name in ranked.columns]
    if "rank_score" not in columns:
        columns.insert(0, "rank_score")
    print(ranked[columns].to_string(index=False))


if __name__ == "__main__":
    main()
