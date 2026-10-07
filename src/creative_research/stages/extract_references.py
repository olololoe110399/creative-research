from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from creative_research.pathing import resolve_path
from creative_research.reference_pack import (
    build_reference_rows,
    copy_reference_media,
    load_master,
    select_reference_candidates,
    write_reference_pack,
)
from creative_research.reference_workspace import write_reference_workspace
from creative_research.system_map import build_system_map


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a portable ranked creative reference pack from creative_master."
    )
    parser.add_argument("master")
    parser.add_argument("--out", default="data/07_exports/reference-pack")
    parser.add_argument("--rank", choices=["relative", "breakout", "saves", "balanced"], default="relative")
    parser.add_argument("--content-type", choices=["all", "slideshow", "video"], default="slideshow")
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
    args = parser.parse_args()

    source_path, master = load_master(args.master)
    population, selected = select_reference_candidates(
        master,
        strategy=args.strategy,
        rank=args.rank,
        content_type=args.content_type,
        top=args.top,
    )
    references = build_reference_rows(
        selected,
        rank_mode=args.rank,
        selection_strategy=args.strategy,
    )
    out_dir = resolve_path(args.out)

    media_dir = out_dir / "media"
    if media_dir.exists():
        shutil.rmtree(media_dir)
    if args.media in {"copy", "hybrid"}:
        references = copy_reference_media(references, out_dir)

    manifest = write_reference_pack(
        references,
        source_master=source_path,
        out_dir=out_dir,
        rank_mode=args.rank,
        content_type=args.content_type,
        media_mode=args.media,
        selection_strategy=args.strategy,
    )
    system_map = build_system_map(
        master,
        population,
        references,
        strategy=args.strategy,
        content_type=args.content_type,
    )
    workspace = write_reference_workspace(
        references,
        selected,
        system_population=population,
        system_map=system_map,
        out_dir=out_dir,
        media_mode=args.media,
    )
    manifest["workspace"] = workspace
    manifest["workspace_entrypoint"] = "index.html"
    manifest["details_dir"] = "details"
    manifest["population"] = "population.jsonl"
    manifest["population_ui"] = "population.json"
    manifest["system_map"] = "system.json"
    manifest["candidate_groups"] = "candidate_groups.json"
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(out_dir)
    print(
        "Open workspace: uv run creative-research references "
        f"--dir {out_dir} --open"
    )


if __name__ == "__main__":
    main()
