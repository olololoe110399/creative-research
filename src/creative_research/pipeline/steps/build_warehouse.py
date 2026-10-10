#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.build_warehouse import (
    build_warehouse,
)
from creative_research.constants import DEFAULT_MASTER_PATH, WAREHOUSE_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text
from creative_research.operating.registry import load_operator_registry


def run(
    *,
    master: str = str(DEFAULT_MASTER_PATH),
    operators: str,
    out: str = "data/05_master",
    allow_unmapped: bool = False,
) -> None:

    master_path = resolve_path(master)
    registry_path = resolve_path(operators)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    master_frame = read_table(master_path)
    registry = load_operator_registry(registry_path)
    tables = build_warehouse(master_frame, registry, allow_unmapped=allow_unmapped)

    outputs: dict[str, str] = {}
    for name, frame in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, frame)
        outputs[name] = str(path)

    post_uids = tables["posts"]["post_uid"]
    if post_uids.duplicated().any():
        raise SystemExit("Warehouse post_uid collision detected")

    report = {
        "warehouse_schema_version": WAREHOUSE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "master": str(master_path),
        "operator_registry": str(registry_path),
        "operators": int(len(tables["operators"])),
        "accounts": int(len(tables["accounts"])),
        "posts": int(len(tables["posts"])),
        "creative_analysis_rows": int(len(tables["creative_analysis"])),
        "creative_sequence_rows": int(len(tables["creative_sequence"])),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No Vision/LLM call was performed.",
            "creative_master remains unchanged and supported.",
        ],
    }
    atomic_write_text(
        out_dir / "warehouse_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
