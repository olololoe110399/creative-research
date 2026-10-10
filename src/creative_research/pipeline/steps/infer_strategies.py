#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.infer_strategies import (
    STRATEGY_SCHEMA_VERSION,
    build_strategy_hypothesis_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    patterns: str = "data/06_analytics/patterns.parquet",
    pattern_evidence: str = "data/06_analytics/pattern_evidence_links.parquet",
    out: str = "data/06_analytics",
) -> None:

    patterns_path = resolve_path(patterns)
    evidence_path = resolve_path(pattern_evidence)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    patterns_frame = read_table(patterns_path)
    evidence = read_table(evidence_path) if evidence_path.exists() else None
    tables = build_strategy_hypothesis_tables(patterns_frame, evidence)

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        write_parquet(path, table)
        outputs[name] = str(path)

    hypotheses = tables["strategy_hypotheses"]
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "hypotheses": int(len(hypotheses)),
        "hypothesis_types": (
            {
                str(key): int(value)
                for key, value in hypotheses["hypothesis_type"].value_counts().items()
            }
            if "hypothesis_type" in hypotheses.columns
            else {}
        ),
        "confidence_bands": (
            {
                str(key): int(value)
                for key, value in hypotheses["confidence_band"].value_counts().items()
            }
            if "confidence_band" in hypotheses.columns
            else {}
        ),
        "strategy_pattern_links": int(len(tables["strategy_pattern_links"])),
        "strategy_evidence_links": int(len(tables["strategy_evidence_links"])),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "All outputs remain hypotheses with causal_claim=false.",
            "Counter evidence and alternative explanations are preserved for review.",
        ],
    }
    atomic_write_text(
        out_dir / "strategy_hypotheses_report.json",
        json.dumps(report, ensure_ascii=False, indent=2),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
