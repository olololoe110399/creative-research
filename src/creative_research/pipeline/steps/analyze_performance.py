#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.analyze_performance import (
    build_performance_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    posts: str = "data/05_master/posts.parquet",
    out: str = "data/06_analytics",
) -> None:

    posts_path = resolve_path(posts)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    posts_frame = read_table(posts_path)
    tables = build_performance_tables(posts_frame)

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, table)
        outputs[name] = str(path)

    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(posts_path),
        "posts": int(len(posts_frame)),
        "accounts": int(posts_frame["account_id"].nunique())
        if "account_id" in posts_frame.columns
        else 0,
        "operators": int(posts_frame["operator_id"].nunique())
        if "operator_id" in posts_frame.columns
        else 0,
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No realtime metrics were collected.",
            "No LLM/Vision call was performed.",
            "Percentiles are relative to the observed historical dataset.",
        ],
    }
    atomic_write_text(
        out_dir / "performance_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
