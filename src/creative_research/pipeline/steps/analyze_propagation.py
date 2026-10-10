#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.analyze_propagation import (
    PROPAGATION_SCHEMA_VERSION,
    build_propagation_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    members: str = "data/06_analytics/creative_family_members.parquet",
    analysis: str = "data/05_master/creative_analysis.parquet",
    performance: str = "data/06_analytics/post_performance.parquet",
    out: str = "data/06_analytics",
) -> None:

    members_path = resolve_path(members)
    analysis_path = resolve_path(analysis)
    performance_path = resolve_path(performance)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    members_frame = read_table(members_path)
    analysis_frame = read_table(analysis_path) if analysis_path.exists() else None
    performance_frame = read_table(performance_path) if performance_path.exists() else None

    tables = build_propagation_tables(members_frame, analysis_frame, performance_frame)
    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, table)
        outputs[name] = str(path)

    events = tables["cross_account_propagation"]
    role_evidence = tables["account_role_evidence"]
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "propagation_schema_version": PROPAGATION_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "members_source": str(members_path),
        "analysis_source": str(analysis_path) if analysis_frame is not None else None,
        "performance_source": (str(performance_path) if performance_frame is not None else None),
        "family_members": int(len(members_frame)),
        "families": int(members_frame["family_id"].nunique()),
        "cross_account_propagation_events": int(len(events)),
        "accounts_with_role_evidence": int(len(role_evidence)),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Propagation means observed later appearance inside an evidence-backed family, not causation.",
            "Account role signals are conditioned on cross-account family flow so singleton families do not dominate origin/receiver evidence.",
            "Role evidence is descriptive and does not assign testing/scaling/conversion strategy labels.",
        ],
    }
    atomic_write_text(
        out_dir / "propagation_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
