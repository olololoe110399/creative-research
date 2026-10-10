#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from creative_research.analysis.quality_audit import build_quality_report
from creative_research.infrastructure.paths import project_root, resolve_path
from creative_research.infrastructure.storage import read_table, write_json
from creative_research.pipeline.build import (
    PipelineConfig,
    build_stage_specs,
    stage_freshness,
)
from creative_research.pipeline.contracts import DEFAULT_WORKSPACE
from creative_research.workspaces.lab import validate_intelligence_workspace


def _read_optional(path: Path) -> pd.DataFrame | None:
    return read_table(path) if path.exists() else None


def run(
    *,
    root: str | None = None,
    operators: str = "config/operators.toml",
    reviews: str | None = None,
    timezone: str = "UTC",
    workspace: str = DEFAULT_WORKSPACE,
    out: str | None = None,
    strict: bool = False,
) -> None:
    config = PipelineConfig.from_paths(
        root=resolve_path(root) if root else project_root(),
        operators=operators,
        reviews=reviews,
        timezone=timezone,
        workspace_out=workspace,
        quality_out=out,
    )
    root_dir = config.root
    workspace_dir = config.workspace_out
    out_path = config.quality_out

    master = root_dir / "data/05_master"
    analytics = root_dir / "data/06_analytics"
    knowledge = root_dir / "data/07_knowledge"

    freshness: dict[str, dict[str, str]] = {}
    for spec in build_stage_specs(config):
        if spec.name in {"audit", "outcome"}:
            continue
        action, reason = stage_freshness(spec)
        freshness[spec.name] = {
            "action": action,
            "reason": reason,
        }

    frames = {
        "operators": _read_optional(master / "operators.parquet"),
        "accounts": _read_optional(master / "accounts.parquet"),
        "posts": _read_optional(master / "posts.parquet"),
        "analysis": _read_optional(master / "creative_analysis.parquet"),
        "performance": _read_optional(analytics / "post_performance.parquet"),
        "cadence": _read_optional(analytics / "posting_cadence.parquet"),
        "families": _read_optional(analytics / "creative_families.parquet"),
        "family_members": _read_optional(analytics / "creative_family_members.parquet"),
        "propagation": _read_optional(analytics / "cross_account_propagation.parquet"),
        "patterns": _read_optional(analytics / "patterns.parquet"),
        "pattern_evidence": _read_optional(analytics / "pattern_evidence_links.parquet"),
        "strategies": _read_optional(analytics / "strategy_hypotheses.parquet"),
        "strategy_pattern_links": _read_optional(analytics / "strategy_pattern_links.parquet"),
        "strategy_evidence_links": _read_optional(analytics / "strategy_evidence_links.parquet"),
        "knowledge": _read_optional(knowledge / "knowledge_catalog.parquet"),
        "knowledge_source_links": _read_optional(knowledge / "knowledge_source_links.parquet"),
        "knowledge_evidence_links": _read_optional(knowledge / "knowledge_evidence_links.parquet"),
    }
    report = build_quality_report(
        **frames,
        workspace_missing_files=validate_intelligence_workspace(workspace_dir),
        stage_freshness_map=freshness,
    )
    published_report = {
        **report,
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root_dir),
        "workspace": str(workspace_dir),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, published_report)
    print(json.dumps(published_report, ensure_ascii=False, indent=2))

    if report["status"] == "fail":
        raise SystemExit(1)
    if strict and report["status"] == "warn":
        raise SystemExit(2)
