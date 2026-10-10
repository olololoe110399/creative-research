#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from creative_research.analysis.build_families import (
    DEFAULT_BRIDGE_FLOOR,
    DEFAULT_THRESHOLD,
    FAMILY_SCHEMA_VERSION,
    build_creative_family_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    posts: str = "data/05_master/posts.parquet",
    analysis: str = "data/05_master/creative_analysis.parquet",
    sequence: str = "data/05_master/creative_sequence.parquet",
    performance: str = "data/06_analytics/post_performance.parquet",
    out: str = "data/06_analytics",
    family_model: str = "v2",
    ai_judgments: str = "data/06_analytics/family_ai/family_ai_judgments.parquet",
    calibration_max_pairs: int = 50000,
    threshold: float = DEFAULT_THRESHOLD,
    bridge_floor: float = DEFAULT_BRIDGE_FLOOR,
    progress_every: int = 100,
) -> None:

    posts_path = resolve_path(posts)
    analysis_path = resolve_path(analysis)
    sequence_path = resolve_path(sequence)
    performance_path = resolve_path(performance)
    ai_judgments_path = resolve_path(ai_judgments)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    posts_frame = read_table(posts_path)
    analysis_frame = read_table(analysis_path)
    sequence_frame = read_table(sequence_path)
    performance_frame = read_table(performance_path) if performance_path.exists() else None
    ai_judgments_frame = read_table(ai_judgments_path) if ai_judgments_path.exists() else None

    clustering_stats: dict[str, Any] = {}
    v2_meta: dict[str, Any] | None = None

    def progress(
        processed: int,
        total: int,
        family_count: int,
        stats: dict[str, int],
    ) -> None:
        pruned = stats.get("anchor_pruned", 0) + stats.get("member_pruned", 0)
        print(
            "Family clustering: "
            f"{processed}/{total} posts · "
            f"{family_count} families · "
            f"{stats.get('full_comparisons', 0)} full comparisons · "
            f"{pruned} pruned",
            flush=True,
        )

    if family_model == "v2":
        from creative_research.analysis.build_families_v2 import (
            build_creative_family_tables_v2,
        )

        print(
            "Family v2: rebuilding legacy positive controls, blocked calibration "
            "candidates, and hybrid core families (no AI API calls).",
            flush=True,
        )
        tables, v2_meta = build_creative_family_tables_v2(
            posts_frame,
            analysis_frame,
            sequence_frame,
            performance_frame,
            ai_judgments_frame,
            calibration_max_pairs=max(1, calibration_max_pairs),
            legacy_threshold=threshold,
            legacy_bridge_floor=bridge_floor,
        )
        clustering_stats = {
            "family_model": "v2",
            "calibration_max_pairs": max(1, calibration_max_pairs),
        }
    else:
        tables = build_creative_family_tables(
            posts_frame,
            analysis_frame,
            sequence_frame,
            performance_frame,
            threshold=threshold,
            bridge_floor=bridge_floor,
            clustering_stats=clustering_stats,
            progress_every=max(0, progress_every),
            progress_callback=progress,
        )

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, table)
        outputs[name] = str(path)

    families = tables["creative_families"]
    members = tables["creative_family_members"]
    multi_post_families = (
        int(families["member_count"].gt(1).sum()) if "member_count" in families.columns else 0
    )
    cross_account_families = (
        int(families["cross_account"].fillna(False).astype(bool).sum())
        if "cross_account" in families.columns
        else 0
    )

    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "family_schema_version": (
            "creative-family-v2" if family_model == "v2" else FAMILY_SCHEMA_VERSION
        ),
        "family_model": family_model,
        "generated_at": datetime.now(UTC).isoformat(),
        "posts_source": str(posts_path),
        "analysis_source": str(analysis_path),
        "sequence_source": str(sequence_path),
        "performance_source": str(performance_path) if performance_frame is not None else None,
        "ai_judgments_source": (str(ai_judgments_path) if ai_judgments_frame is not None else None),
        "posts": int(len(posts_frame)),
        "families": int(len(families)),
        "multi_post_families": multi_post_families,
        "cross_account_families": cross_account_families,
        "family_members": int(len(members)),
        "threshold": (v2_meta.get("strong_combined") if v2_meta is not None else threshold),
        "bridge_floor": (v2_meta.get("bridge_combined") if v2_meta is not None else bridge_floor),
        "clustering_stats": clustering_stats,
        "v2_meta": v2_meta,
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Family v2 may consume precomputed AI judgments as durable inferred evidence but never calls an AI API.",
            "Families are evidence-backed core-concept candidates, not causal or strategic claims.",
            "Every assignment retains stable post_uid lineage plus deterministic/AI gate provenance.",
        ],
    }
    atomic_write_text(
        out_dir / "creative_families_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
