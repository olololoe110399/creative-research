from __future__ import annotations

import argparse
import json
from pathlib import Path

from creative_research.pathing import resolve_path
from creative_research.reference_pack import (
    build_reference_rows,
    copy_reference_media,
    load_master,
    rank_master,
    write_reference_pack,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a portable ranked creative reference pack from creative_master."
    )
    parser.add_argument("master")
    parser.add_argument("--out", default="data/07_exports/reference-pack")
    parser.add_argument("--rank", choices=["relative", "breakout", "saves", "balanced"], default="relative")
    parser.add_argument("--content-type", choices=["all", "slideshow", "video"], default="slideshow")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--media", choices=["none", "copy"], default="none")
    args = parser.parse_args()

    source_path, master = load_master(args.master)
    ranked = rank_master(master, rank=args.rank, content_type=args.content_type, top=args.top)
    references = build_reference_rows(ranked, rank_mode=args.rank)
    out_dir = resolve_path(args.out)
    if args.media == "copy":
        references = copy_reference_media(references, out_dir)

    manifest = write_reference_pack(
        references,
        source_master=source_path,
        out_dir=out_dir,
        rank_mode=args.rank,
        content_type=args.content_type,
        media_mode=args.media,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(out_dir)


if __name__ == "__main__":
    main()
