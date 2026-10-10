#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.analyze_timeline import (
    TIMELINE_SCHEMA_VERSION,
    build_strategy_timeline_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    posts: str = "data/05_master/posts.parquet",
    analysis: str = "data/05_master/creative_analysis.parquet",
    performance: str = "data/06_analytics/post_performance.parquet",
    cadence: str = "data/06_analytics/posting_cadence.parquet",
    family_members: str = "data/06_analytics/creative_family_members.parquet",
    family_entries: str = "data/06_analytics/family_account_entries.parquet",
    out: str = "data/06_analytics",
    frequency: str = "month",
    timezone: str = "UTC",
    min_posts: int = 5,
    change_threshold: float = 0.24,
) -> None:

    paths = {
        "posts": resolve_path(posts),
        "analysis": resolve_path(analysis),
        "performance": resolve_path(performance),
        "cadence": resolve_path(cadence),
        "family_members": resolve_path(family_members),
        "family_entries": resolve_path(family_entries),
    }
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    posts_frame = read_table(paths["posts"])
    analysis_frame = read_table(paths["analysis"])
    optional = {
        key: read_table(path) if path.exists() else None
        for key, path in paths.items()
        if key not in {"posts", "analysis"}
    }

    tables = build_strategy_timeline_tables(
        posts_frame,
        analysis_frame,
        optional.get("performance"),
        optional.get("cadence"),
        optional.get("family_members"),
        optional.get("family_entries"),
        frequency=frequency,
        timezone=timezone,
        min_posts=min_posts,
        change_threshold=change_threshold,
    )

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, table)
        outputs[name] = str(path)

    changes = tables["strategy_change_points"]
    flagged = (
        int(changes["is_change_point"].fillna(False).astype(bool).sum())
        if "is_change_point" in changes.columns
        else 0
    )
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "timeline_schema_version": TIMELINE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "frequency": frequency,
        "timezone": timezone,
        "min_posts": min_posts,
        "change_threshold": change_threshold,
        "strategy_windows": int(len(tables["strategy_windows"])),
        "change_comparisons": int(len(changes)),
        "flagged_change_points": flagged,
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Change points are deterministic adjacent-window differences, not semantic strategy labels.",
        ],
    }
    atomic_write_text(
        out_dir / "strategy_timeline_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
