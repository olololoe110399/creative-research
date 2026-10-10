#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.promote_knowledge import (
    KNOWLEDGE_SCHEMA_VERSION,
    _write_jsonl,
    build_knowledge_tables,
)
from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.infrastructure.knowledge_reviews import (
    load_knowledge_reviews,
)
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    hypotheses: str = "data/06_analytics/strategy_hypotheses.parquet",
    strategy_evidence: str = "data/06_analytics/strategy_evidence_links.parquet",
    families: str = "data/06_analytics/creative_families.parquet",
    family_members: str = "data/06_analytics/creative_family_members.parquet",
    reviews: str | None = None,
    min_confidence: float = 0.6,
    out: str = "data/07_knowledge",
) -> None:

    paths = {
        "hypotheses": resolve_path(hypotheses),
        "strategy_evidence": resolve_path(strategy_evidence),
        "families": resolve_path(families),
        "family_members": resolve_path(family_members),
    }
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    hypotheses_frame = read_table(paths["hypotheses"])
    strategy_evidence_frame = (
        read_table(paths["strategy_evidence"]) if paths["strategy_evidence"].exists() else None
    )
    families_frame = read_table(paths["families"]) if paths["families"].exists() else None
    family_members_frame = (
        read_table(paths["family_members"]) if paths["family_members"].exists() else None
    )
    reviews_path = resolve_path(reviews) if reviews else None
    reviews_frame = load_knowledge_reviews(reviews_path)

    tables = build_knowledge_tables(
        hypotheses_frame,
        strategy_evidence_frame,
        families_frame,
        family_members_frame,
        reviews=reviews_frame,
        min_confidence=min_confidence,
    )

    outputs: dict[str, dict[str, str]] = {}
    for name, table in tables.items():
        parquet_path = out_dir / f"{name}.parquet"
        jsonl_path = out_dir / f"{name}.jsonl"
        write_parquet(parquet_path, table)
        _write_jsonl(jsonl_path, table)
        outputs[name] = {
            "parquet": str(parquet_path),
            "jsonl": str(jsonl_path),
        }

    catalog = tables["knowledge_catalog"]
    status_counts = (
        {str(key): int(value) for key, value in catalog["knowledge_status"].value_counts().items()}
        if "knowledge_status" in catalog.columns
        else {}
    )
    type_counts = (
        {str(key): int(value) for key, value in catalog["knowledge_type"].value_counts().items()}
        if "knowledge_type" in catalog.columns
        else {}
    )
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "min_confidence": min_confidence,
        "reviews_source": str(reviews_path) if reviews_path else None,
        "knowledge_items": int(len(catalog)),
        "type_counts": type_counts,
        "status_counts": status_counts,
        "source_links": int(len(tables["knowledge_source_links"])),
        "evidence_links": int(len(tables["knowledge_evidence_links"])),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Promoted items remain scope-bound evidence-derived knowledge, not universal truth.",
            "Review candidates should be approved before high-impact downstream automation.",
        ],
    }
    atomic_write_text(
        out_dir / "knowledge_report.json", json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
