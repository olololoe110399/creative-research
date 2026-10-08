#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from creative_research.intelligence_workspace import write_intelligence_workspace
from creative_research.validation import read_table

DEFAULTS = {
    "operators": "data/05_master/operators.parquet",
    "accounts": "data/05_master/accounts.parquet",
    "posts": "data/05_master/posts.parquet",
    "creative_analysis": "data/05_master/creative_analysis.parquet",
    "creative_sequence": "data/05_master/creative_sequence.parquet",
    "performance": "data/06_analytics/post_performance.parquet",
    "account_baselines": "data/06_analytics/account_performance_baselines.parquet",
    "account_cadence": "data/06_analytics/account_cadence_summary.parquet",
    "role_evidence": "data/06_analytics/account_role_evidence.parquet",
    "strategy_windows": "data/06_analytics/strategy_windows.parquet",
    "strategy_changes": "data/06_analytics/strategy_change_points.parquet",
    "families": "data/06_analytics/creative_families.parquet",
    "family_members": "data/06_analytics/creative_family_members.parquet",
    "propagation": "data/06_analytics/cross_account_propagation.parquet",
    "patterns": "data/06_analytics/patterns.parquet",
    "pattern_evidence_links": "data/06_analytics/pattern_evidence_links.parquet",
    "strategies": "data/06_analytics/strategy_hypotheses.parquet",
    "strategy_pattern_links": "data/06_analytics/strategy_pattern_links.parquet",
    "strategy_evidence_links": "data/06_analytics/strategy_evidence_links.parquet",
    "knowledge": "data/07_knowledge/knowledge_catalog.parquet",
    "knowledge_source_links": "data/07_knowledge/knowledge_source_links.parquet",
    "knowledge_evidence_links": "data/07_knowledge/knowledge_evidence_links.parquet",
}


def _read_optional(path: Path) -> pd.DataFrame | None:
    return read_table(path) if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a static Operator Intelligence Workspace from existing warehouse, "
            "analytics, strategy, and knowledge outputs. No expensive stage is rerun."
        )
    )
    for name, default in DEFAULTS.items():
        parser.add_argument(
            "--" + name.replace("_", "-"),
            default=default,
        )
    parser.add_argument(
        "--out",
        default="data/07_exports/operator-intelligence",
    )
    args = parser.parse_args()

    frames: dict[str, pd.DataFrame | None] = {}
    sources: dict[str, str] = {}
    for name in DEFAULTS:
        raw = getattr(args, name)
        path = Path(raw).expanduser().resolve()
        sources[name] = str(path)
        frames[name] = _read_optional(path)

    required = ("operators", "accounts", "posts", "creative_analysis")
    missing = [name for name in required if frames[name] is None]
    if missing:
        raise SystemExit(
            "Missing required intelligence inputs: " + ", ".join(missing)
        )

    report = write_intelligence_workspace(
        out_dir=Path(args.out).expanduser().resolve(),
        sources=sources,
        **frames,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
