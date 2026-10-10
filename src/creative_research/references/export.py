from __future__ import annotations

import json
from collections.abc import Sequence

from creative_research.analysis.system_map import build_system_map
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import replace_directory
from creative_research.infrastructure.storage import write_text as atomic_write_text
from creative_research.references.pack import (
    DEFAULT_GROUP_DIMENSIONS,
    apply_conditions,
    build_reference_rows,
    copy_reference_media,
    group_references,
    load_master,
    rank_master,
    select_reference_candidates,
    write_reference_pack,
    write_table,
)
from creative_research.workspaces.references import write_reference_workspace


def export_references(
    *,
    master: str,
    out: str = "data/07_exports/reference-pack",
    rank: str = "relative",
    content_type: str = "slideshow",
    top: int = 30,
    strategy: str = "system",
    media: str = "remote",
) -> None:

    source_path, master_frame = load_master(master)
    population, selected = select_reference_candidates(
        master_frame,
        strategy=strategy,
        rank=rank,
        content_type=content_type,
        top=top,
    )
    references = build_reference_rows(
        selected,
        rank_mode=rank,
        selection_strategy=strategy,
    )
    out_dir = resolve_path(out)

    if media in {"copy", "hybrid"}:
        references = copy_reference_media(references, out_dir)
    else:
        with replace_directory(out_dir / "media"):
            pass  # Empty current media namespace; prior assets remain in the retained backup.

    manifest = write_reference_pack(
        references,
        source_master=source_path,
        out_dir=out_dir,
        rank_mode=rank,
        content_type=content_type,
        media_mode=media,
        selection_strategy=strategy,
    )
    system_map = build_system_map(
        master_frame,
        population,
        references,
        strategy=strategy,
        content_type=content_type,
    )
    workspace = write_reference_workspace(
        references,
        selected,
        system_population=population,
        system_map=system_map,
        out_dir=out_dir,
        media_mode=media,
    )
    manifest["workspace"] = workspace
    manifest["workspace_entrypoint"] = "index.html"
    manifest["details_dir"] = "details"
    manifest["population"] = "population.jsonl"
    manifest["population_ui"] = "population.json"
    manifest["system_map"] = "system.json"
    manifest["candidate_groups"] = "candidate_groups.json"
    atomic_write_text(out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(out_dir)
    print(f"Open workspace: uv run creative-research references --dir {out_dir} --open")


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


def rank_posts(
    *,
    master: str,
    rank: str = "relative",
    content_type: str = "all",
    top: int = 50,
    out: str | None = None,
) -> None:

    _, master_frame = load_master(master)
    ranked = rank_master(master_frame, rank=rank, content_type=content_type, top=top)
    if out:
        path = resolve_path(out)
        write_table(ranked, path)
        print(path)
        return

    columns = [name for name in DISPLAY_COLUMNS if name in ranked.columns]
    if "rank_score" not in columns:
        columns.insert(0, "rank_score")
    print(ranked[columns].to_string(index=False))


def export_groups(
    *,
    references: str,
    dimensions: str = ",".join(DEFAULT_GROUP_DIMENSIONS),
    out: str | None = None,
) -> None:

    source_path, df = load_master(references)
    dimensions_frame = [value.strip() for value in dimensions.split(",") if value.strip()]
    result = group_references(df, dimensions=dimensions_frame)
    out_path = resolve_path(out) if out else source_path.with_name("candidate_groups.csv")
    write_table(result, out_path)
    print(out_path)


def query_table(
    *,
    table: str,
    where: Sequence[str] = (),
    columns: str | None = None,
    limit: int | None = None,
    out: str | None = None,
) -> None:

    _, df = load_master(table)
    result = apply_conditions(df, list(where))
    if columns:
        selected_columns = [value.strip() for value in columns.split(",") if value.strip()]
        missing = [name for name in selected_columns if name not in result.columns]
        if missing:
            raise SystemExit("Unknown output columns: " + ", ".join(missing))
        result = result[selected_columns]
    if limit is not None:
        result = result.head(limit)

    if out:
        path = resolve_path(out)
        write_table(result, path)
        print(path)
    else:
        print(result.to_string(index=False))
