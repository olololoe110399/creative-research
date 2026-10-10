#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.discover_patterns import (
    PATTERN_SCHEMA_VERSION,
    build_pattern_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    analysis: str = "data/05_master/creative_analysis.parquet",
    performance: str = "data/06_analytics/post_performance.parquet",
    cadence: str = "data/06_analytics/posting_cadence.parquet",
    families: str = "data/06_analytics/creative_families.parquet",
    family_members: str = "data/06_analytics/creative_family_members.parquet",
    propagation: str = "data/06_analytics/cross_account_propagation.parquet",
    role_evidence: str = "data/06_analytics/account_role_evidence.parquet",
    strategy_changes: str = "data/06_analytics/strategy_change_points.parquet",
    strategy_members: str = "data/06_analytics/strategy_window_members.parquet",
    out: str = "data/06_analytics",
    min_sample: int = 5,
    min_performance_effect: float = 0.1,
    min_cadence_effect: float = 0.25,
    propagation_dominant_rate: float = 0.7,
) -> None:

    paths = {
        "analysis": resolve_path(analysis),
        "performance": resolve_path(performance),
        "cadence": resolve_path(cadence),
        "families": resolve_path(families),
        "family_members": resolve_path(family_members),
        "propagation": resolve_path(propagation),
        "role_evidence": resolve_path(role_evidence),
        "strategy_changes": resolve_path(strategy_changes),
        "strategy_members": resolve_path(strategy_members),
    }

    frames = {key: read_table(path) if path.exists() else None for key, path in paths.items()}
    tables = build_pattern_tables(
        frames["analysis"],
        frames["performance"],
        frames["cadence"],
        frames["families"],
        frames["family_members"],
        frames["propagation"],
        frames["role_evidence"],
        frames["strategy_changes"],
        frames["strategy_members"],
        min_sample=min_sample,
        min_performance_effect=min_performance_effect,
        min_cadence_effect=min_cadence_effect,
        propagation_dominant_rate=propagation_dominant_rate,
    )

    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, table)
        outputs[name] = str(path)

    patterns = tables["patterns"]
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "pattern_schema_version": PATTERN_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "patterns": int(len(patterns)),
        "pattern_types": (
            {str(key): int(value) for key, value in patterns["pattern_type"].value_counts().items()}
            if "pattern_type" in patterns.columns
            else {}
        ),
        "evidence_links": int(len(tables["pattern_evidence_links"])),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Patterns are structured observations, not rules, playbooks, or causal claims.",
        ],
    }
    atomic_write_text(
        out_dir / "patterns_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
