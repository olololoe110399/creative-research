"""Build canonical evidence tables from existing Vision outputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.build_master import build_master
from creative_research.analysis.validation import validate_master
from creative_research.constants import MASTER_SCHEMA_VERSION
from creative_research.infrastructure.paths import portable_path, resolve_path
from creative_research.infrastructure.storage import (
    atomic_output,
    read_table,
    write_csv,
    write_parquet,
)
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    slides: str,
    videos: str,
    out: str = "data/05_master",
) -> None:

    slides_path = resolve_path(slides)
    videos_path = resolve_path(videos)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    master = build_master(read_table(slides_path), read_table(videos_path))
    validation = validate_master(master)
    if not validation.ok:
        messages = "\n".join(f"- {issue.code}: {issue.message}" for issue in validation.issues)
        raise SystemExit(f"Master validation failed before write:\n{messages}")

    parquet_path = out_dir / "creative_master.parquet"
    csv_path = out_dir / "creative_master.csv"
    jsonl_path = out_dir / "creative_master.jsonl"

    write_parquet(parquet_path, master)
    write_csv(csv_path, master, index=False, encoding="utf-8-sig")
    with atomic_output(jsonl_path) as temporary:
        master.to_json(
            temporary,
            orient="records",
            lines=True,
            force_ascii=False,
            date_format="iso",
        )

    report = {
        "master_schema_version": MASTER_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "slides_input": portable_path(slides_path),
        "videos_input": portable_path(videos_path),
        "rows": int(len(master)),
        "slideshows": int((master["content_type"] == "slideshow").sum()),
        "videos": int((master["content_type"] == "video").sum()),
        "accounts": int(master["account"].nunique()),
        "created_at_min": (
            None if master["created_at"].isna().all() else master["created_at"].min().isoformat()
        ),
        "created_at_max": (
            None if master["created_at"].isna().all() else master["created_at"].max().isoformat()
        ),
        "validation": validation.as_dict(),
        "output": portable_path(out_dir),
    }
    atomic_write_text(out_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(parquet_path)
