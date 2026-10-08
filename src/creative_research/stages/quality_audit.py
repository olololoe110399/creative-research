#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.intelligence_pipeline import (
    PipelineConfig,
    build_stage_specs,
    stage_freshness,
)
from creative_research.intelligence_workspace import validate_intelligence_workspace
from creative_research.validation import read_table

QUALITY_SCHEMA_VERSION = "intelligence-quality-v1"


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _unique_values(frame: pd.DataFrame | None, column: str) -> set[str]:
    if frame is None or frame.empty or column not in frame.columns:
        return set()
    return {
        str(value)
        for value in frame[column].dropna().astype(str)
        if str(value)
    }


def _duplicates(frame: pd.DataFrame | None, column: str) -> int:
    if frame is None or frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].dropna().astype(str).duplicated().sum())


def _nonnull_count(frame: pd.DataFrame | None, column: str) -> int:
    if frame is None or frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].notna().sum())


def _issue(
    issues: list[dict[str, Any]],
    *,
    level: str,
    code: str,
    message: str,
    metric: float | int | str | None = None,
) -> None:
    issues.append(
        {
            "level": level,
            "code": code,
            "message": message,
            "metric": metric,
        }
    )


def _coverage_check(
    issues: list[dict[str, Any]],
    *,
    code: str,
    label: str,
    covered: int,
    total: int,
    warn_below: float = 0.95,
    fail_below: float = 0.80,
) -> float | None:
    rate = _safe_rate(covered, total)
    if rate is None:
        _issue(
            issues,
            level="fail",
            code=code,
            message=f"Cannot calculate {label}: denominator is zero.",
        )
        return None
    if rate < fail_below:
        _issue(
            issues,
            level="fail",
            code=code,
            message=f"{label} is {rate:.1%}, below failure threshold {fail_below:.0%}.",
            metric=rate,
        )
    elif rate < warn_below:
        _issue(
            issues,
            level="warn",
            code=code,
            message=f"{label} is {rate:.1%}, below warning threshold {warn_below:.0%}.",
            metric=rate,
        )
    return rate


def _orphan_count(values: set[str], valid: set[str]) -> int:
    return len(values - valid)


def build_quality_report(
    *,
    operators: pd.DataFrame | None,
    accounts: pd.DataFrame | None,
    posts: pd.DataFrame | None,
    analysis: pd.DataFrame | None,
    performance: pd.DataFrame | None,
    cadence: pd.DataFrame | None,
    families: pd.DataFrame | None,
    family_members: pd.DataFrame | None,
    propagation: pd.DataFrame | None,
    patterns: pd.DataFrame | None,
    pattern_evidence: pd.DataFrame | None,
    strategies: pd.DataFrame | None,
    strategy_pattern_links: pd.DataFrame | None,
    strategy_evidence_links: pd.DataFrame | None,
    knowledge: pd.DataFrame | None,
    knowledge_source_links: pd.DataFrame | None,
    knowledge_evidence_links: pd.DataFrame | None,
    workspace_missing_files: list[str] | None = None,
    stage_freshness_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    counts = {
        "operators": int(len(operators)) if operators is not None else 0,
        "accounts": int(len(accounts)) if accounts is not None else 0,
        "posts": int(len(posts)) if posts is not None else 0,
        "analysis_rows": int(len(analysis)) if analysis is not None else 0,
        "performance_rows": int(len(performance)) if performance is not None else 0,
        "cadence_rows": int(len(cadence)) if cadence is not None else 0,
        "families": int(len(families)) if families is not None else 0,
        "family_members": int(len(family_members)) if family_members is not None else 0,
        "propagation_events": int(len(propagation)) if propagation is not None else 0,
        "patterns": int(len(patterns)) if patterns is not None else 0,
        "strategies": int(len(strategies)) if strategies is not None else 0,
        "knowledge_items": int(len(knowledge)) if knowledge is not None else 0,
    }

    if counts["posts"] == 0:
        _issue(
            issues,
            level="fail",
            code="posts.empty",
            message="Canonical posts table is empty or missing.",
        )

    id_specs = (
        ("posts", posts, "post_uid"),
        ("accounts", accounts, "account_id"),
        ("operators", operators, "operator_id"),
        ("families", families, "family_id"),
        ("patterns", patterns, "pattern_id"),
        ("strategies", strategies, "hypothesis_id"),
        ("knowledge", knowledge, "knowledge_id"),
    )
    duplicate_counts: dict[str, int] = {}
    for label, frame, column in id_specs:
        duplicate_count = _duplicates(frame, column)
        duplicate_counts[label] = duplicate_count
        if duplicate_count:
            _issue(
                issues,
                level="fail",
                code=f"{label}.duplicate_id",
                message=f"{label} contains {duplicate_count} duplicate {column} values.",
                metric=duplicate_count,
            )

    post_ids = _unique_values(posts, "post_uid")
    account_ids = _unique_values(accounts, "account_id")
    operator_ids = _unique_values(operators, "operator_id")
    family_ids = _unique_values(families, "family_id")
    pattern_ids = _unique_values(patterns, "pattern_id")
    strategy_ids = _unique_values(strategies, "hypothesis_id")
    knowledge_ids = _unique_values(knowledge, "knowledge_id")

    analysis_post_ids = _unique_values(analysis, "post_uid")
    performance_post_ids = _unique_values(performance, "post_uid")
    cadence_post_ids = _unique_values(cadence, "post_uid")
    family_member_post_ids = _unique_values(family_members, "post_uid")

    coverage = {
        "analysis_post_coverage": _coverage_check(
            issues,
            code="coverage.analysis",
            label="Creative analysis post coverage",
            covered=len(post_ids & analysis_post_ids),
            total=len(post_ids),
        ),
        "performance_post_coverage": _coverage_check(
            issues,
            code="coverage.performance",
            label="Performance post coverage",
            covered=len(post_ids & performance_post_ids),
            total=len(post_ids),
        ),
        "cadence_post_coverage": _coverage_check(
            issues,
            code="coverage.cadence",
            label="Cadence post coverage",
            covered=len(post_ids & cadence_post_ids),
            total=len(post_ids),
            warn_below=0.90,
            fail_below=0.70,
        ),
        "family_membership_coverage": _coverage_check(
            issues,
            code="coverage.family_membership",
            label="Creative family membership coverage",
            covered=len(post_ids & family_member_post_ids),
            total=len(post_ids),
            warn_below=0.999,
            fail_below=0.95,
        ),
    }

    if posts is not None and not posts.empty:
        operator_mapped = _nonnull_count(posts, "operator_id")
        coverage["post_operator_mapping"] = _coverage_check(
            issues,
            code="coverage.operator_mapping",
            label="Post-to-operator mapping coverage",
            covered=operator_mapped,
            total=len(posts),
            warn_below=1.0,
            fail_below=0.98,
        )

    family_member_family_ids = _unique_values(family_members, "family_id")
    family_orphans = _orphan_count(family_member_family_ids, family_ids)
    family_post_orphans = _orphan_count(family_member_post_ids, post_ids)
    if family_orphans:
        _issue(
            issues,
            level="fail",
            code="lineage.family_member_family_orphan",
            message=f"{family_orphans} family IDs in family members do not exist in creative_families.",
            metric=family_orphans,
        )
    if family_post_orphans:
        _issue(
            issues,
            level="fail",
            code="lineage.family_member_post_orphan",
            message=f"{family_post_orphans} post IDs in family members do not exist in posts.",
            metric=family_post_orphans,
        )

    if family_members is not None and not family_members.empty and "post_uid" in family_members.columns:
        duplicate_memberships = int(
            family_members["post_uid"].dropna().astype(str).duplicated().sum()
        )
        if duplicate_memberships:
            _issue(
                issues,
                level="fail",
                code="families.multiple_membership",
                message=f"{duplicate_memberships} posts belong to more than one family row.",
                metric=duplicate_memberships,
            )

    if propagation is not None and not propagation.empty:
        for column, valid, code in (
            ("family_id", family_ids, "lineage.propagation_family"),
            ("family_origin_post_uid", post_ids, "lineage.propagation_origin_post"),
            ("target_first_post_uid", post_ids, "lineage.propagation_target_post"),
            ("origin_account_id", account_ids, "lineage.propagation_origin_account"),
            ("target_account_id", account_ids, "lineage.propagation_target_account"),
        ):
            values = _unique_values(propagation, column)
            orphans = _orphan_count(values, valid)
            if orphans:
                _issue(
                    issues,
                    level="fail",
                    code=code,
                    message=f"{orphans} {column} references are orphaned.",
                    metric=orphans,
                )

    if pattern_evidence is not None and not pattern_evidence.empty:
        relations = (
            ("pattern_id", pattern_ids, "lineage.pattern_evidence_pattern"),
            ("post_uid", post_ids, "lineage.pattern_evidence_post"),
            ("family_id", family_ids, "lineage.pattern_evidence_family"),
            ("account_id", account_ids, "lineage.pattern_evidence_account"),
        )
        for column, valid, code in relations:
            values = _unique_values(pattern_evidence, column)
            orphans = _orphan_count(values, valid)
            if orphans:
                _issue(
                    issues,
                    level="fail",
                    code=code,
                    message=f"{orphans} {column} references are orphaned.",
                    metric=orphans,
                )

    if strategy_pattern_links is not None and not strategy_pattern_links.empty:
        for column, valid, code in (
            ("hypothesis_id", strategy_ids, "lineage.strategy_pattern_hypothesis"),
            ("pattern_id", pattern_ids, "lineage.strategy_pattern_pattern"),
        ):
            values = _unique_values(strategy_pattern_links, column)
            orphans = _orphan_count(values, valid)
            if orphans:
                _issue(
                    issues,
                    level="fail",
                    code=code,
                    message=f"{orphans} {column} references are orphaned.",
                    metric=orphans,
                )

    if strategy_evidence_links is not None and not strategy_evidence_links.empty:
        for column, valid, code in (
            ("hypothesis_id", strategy_ids, "lineage.strategy_evidence_hypothesis"),
            ("pattern_id", pattern_ids, "lineage.strategy_evidence_pattern"),
            ("post_uid", post_ids, "lineage.strategy_evidence_post"),
            ("family_id", family_ids, "lineage.strategy_evidence_family"),
            ("account_id", account_ids, "lineage.strategy_evidence_account"),
        ):
            values = _unique_values(strategy_evidence_links, column)
            orphans = _orphan_count(values, valid)
            if orphans:
                _issue(
                    issues,
                    level="fail",
                    code=code,
                    message=f"{orphans} {column} references are orphaned.",
                    metric=orphans,
                )

    if knowledge_source_links is not None and not knowledge_source_links.empty:
        knowledge_orphans = _orphan_count(
            _unique_values(knowledge_source_links, "knowledge_id"),
            knowledge_ids,
        )
        if knowledge_orphans:
            _issue(
                issues,
                level="fail",
                code="lineage.knowledge_source_knowledge",
                message=f"{knowledge_orphans} knowledge source links point to missing knowledge items.",
                metric=knowledge_orphans,
            )
        for row in knowledge_source_links.to_dict(orient="records"):
            source_type = str(row.get("source_type") or "")
            source_id = str(row.get("source_id") or "")
            if not source_id:
                continue
            if source_type in {"hypothesis", "hypothesis_bundle"}:
                valid = strategy_ids
            elif source_type == "family":
                valid = family_ids
            else:
                continue
            if source_id not in valid:
                _issue(
                    issues,
                    level="fail",
                    code="lineage.knowledge_source_orphan",
                    message=f"Knowledge source {source_type}:{source_id} is missing.",
                    metric=source_id,
                )

    if knowledge_evidence_links is not None and not knowledge_evidence_links.empty:
        for column, valid, code in (
            ("knowledge_id", knowledge_ids, "lineage.knowledge_evidence_knowledge"),
            ("pattern_id", pattern_ids, "lineage.knowledge_evidence_pattern"),
            ("post_uid", post_ids, "lineage.knowledge_evidence_post"),
            ("family_id", family_ids, "lineage.knowledge_evidence_family"),
            ("account_id", account_ids, "lineage.knowledge_evidence_account"),
        ):
            values = _unique_values(knowledge_evidence_links, column)
            orphans = _orphan_count(values, valid)
            if orphans:
                _issue(
                    issues,
                    level="fail",
                    code=code,
                    message=f"{orphans} {column} references are orphaned.",
                    metric=orphans,
                )

    if knowledge is not None and not knowledge.empty:
        source_linked = _unique_values(knowledge_source_links, "knowledge_id")
        unlinked = knowledge_ids - source_linked
        if unlinked:
            _issue(
                issues,
                level="warn",
                code="knowledge.missing_source_links",
                message=f"{len(unlinked)} knowledge items have no direct source link.",
                metric=len(unlinked),
            )

        status_counts = {
            str(key): int(value)
            for key, value in knowledge["knowledge_status"].value_counts().items()
        } if "knowledge_status" in knowledge.columns else {}
        active_ids = set(
            knowledge.loc[
                knowledge["knowledge_status"].astype(str).isin(["approved", "promoted"]),
                "knowledge_id",
            ].astype(str)
        ) if "knowledge_status" in knowledge.columns else set()
        if not active_ids:
            _issue(
                issues,
                level="warn",
                code="knowledge.no_active_items",
                message="Knowledge bank contains no approved/promoted active items.",
            )
    else:
        status_counts = {}
        _issue(
            issues,
            level="warn",
            code="knowledge.empty",
            message="Knowledge catalog is empty or missing.",
        )

    if patterns is None or patterns.empty:
        _issue(
            issues,
            level="warn",
            code="patterns.empty",
            message="No evidence patterns were generated.",
        )
    if strategies is None or strategies.empty:
        _issue(
            issues,
            level="warn",
            code="strategies.empty",
            message="No strategy hypotheses were generated.",
        )

    workspace_missing = workspace_missing_files or []
    freshness = stage_freshness_map or {}
    stale_stages = {
        name: value
        for name, value in freshness.items()
        if value.get("action") in {"run", "blocked"}
    }
    for name, value in stale_stages.items():
        action = value.get("action")
        _issue(
            issues,
            level="fail",
            code=f"freshness.{name}",
            message=f"Stage {name} is {action}: {value.get('reason')}",
            metric=action,
        )

    if workspace_missing:
        _issue(
            issues,
            level="fail",
            code="workspace.missing_files",
            message="Intelligence workspace is missing required files: "
            + ", ".join(workspace_missing),
            metric=len(workspace_missing),
        )

    fail_count = sum(1 for issue in issues if issue["level"] == "fail")
    warn_count = sum(1 for issue in issues if issue["level"] == "warn")
    status = "fail" if fail_count else "warn" if warn_count else "pass"

    return {
        "quality_schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "counts": counts,
        "coverage": coverage,
        "duplicate_counts": duplicate_counts,
        "knowledge_status_counts": status_counts,
        "workspace_missing_files": workspace_missing,
        "stage_freshness": freshness,
        "stale_stages": stale_stages,
        "issue_counts": {
            "fail": fail_count,
            "warn": warn_count,
            "total": len(issues),
        },
        "issues": issues,
    }


def _read_optional(path: Path) -> pd.DataFrame | None:
    return read_table(path) if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit deterministic operator-intelligence outputs for coverage, duplicate IDs, "
            "referential integrity, evidence lineage, trust status, and workspace completeness."
        )
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--operators",
        default="config/operators.toml",
        help="Operator registry used for freshness auditing.",
    )
    parser.add_argument(
        "--reviews",
        default=None,
        help="Optional knowledge review TOML used for freshness auditing.",
    )
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument(
        "--workspace",
        default="data/07_exports/operator-intelligence",
    )
    parser.add_argument(
        "--out",
        default="data/07_exports/operator-intelligence/quality_report.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as failures.",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    workspace = Path(args.workspace).expanduser()
    if not workspace.is_absolute():
        workspace = (root / workspace).resolve()
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = (root / out).resolve()

    master = root / "data/05_master"
    analytics = root / "data/06_analytics"
    knowledge = root / "data/07_knowledge"

    operators_path = Path(args.operators).expanduser()
    if not operators_path.is_absolute():
        operators_path = (root / operators_path).resolve()
    reviews_path = Path(args.reviews).expanduser() if args.reviews else None
    if reviews_path is not None and not reviews_path.is_absolute():
        reviews_path = (root / reviews_path).resolve()

    config = PipelineConfig(
        root=root,
        operators=operators_path,
        reviews=reviews_path,
        timezone=args.timezone,
        workspace_out=workspace,
        quality_out=out,
    )
    freshness: dict[str, dict[str, str]] = {}
    for spec in build_stage_specs(config):
        if spec.name == "audit":
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
        "strategy_pattern_links": _read_optional(
            analytics / "strategy_pattern_links.parquet"
        ),
        "strategy_evidence_links": _read_optional(
            analytics / "strategy_evidence_links.parquet"
        ),
        "knowledge": _read_optional(knowledge / "knowledge_catalog.parquet"),
        "knowledge_source_links": _read_optional(
            knowledge / "knowledge_source_links.parquet"
        ),
        "knowledge_evidence_links": _read_optional(
            knowledge / "knowledge_evidence_links.parquet"
        ),
    }
    report = build_quality_report(
        **frames,
        workspace_missing_files=validate_intelligence_workspace(workspace),
        stage_freshness_map=freshness,
    )
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["root"] = str(root)
    report["workspace"] = str(workspace)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["status"] == "fail":
        raise SystemExit(1)
    if args.strict and report["status"] == "warn":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
