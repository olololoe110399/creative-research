from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pandas as pd

WORKSPACE_SCHEMA_VERSION = "operator-intelligence-workspace-v1"
STATIC_FILES = ("index.html", "app.js", "style.css", "favicon.svg")
REQUIRED_DATA_FILES = (
    "workspace.json",
    "overview.json",
    "accounts.json",
    "timeline.json",
    "families.json",
    "patterns.json",
    "strategies.json",
    "knowledge.json",
    "evidence.json",
)


def _clean(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _record(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _clean(value) for key, value in row.items()}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [_record(row) for row in frame.to_dict(orient="records")]


def _parse_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _index_rows(frame: pd.DataFrame | None, key: str) -> dict[str, dict[str, Any]]:
    if frame is None or frame.empty or key not in frame.columns:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict(orient="records"):
        value = row.get(key)
        if value is None:
            continue
        result[str(value)] = _record(row)
    return result


def _group_rows(frame: pd.DataFrame | None, key: str) -> dict[str, list[dict[str, Any]]]:
    if frame is None or frame.empty or key not in frame.columns:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for row in frame.to_dict(orient="records"):
        value = row.get(key)
        if value is None:
            continue
        result.setdefault(str(value), []).append(_record(row))
    return result


def _active_knowledge(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty or "knowledge_status" not in frame.columns:
        return pd.DataFrame()
    return frame.loc[
        frame["knowledge_status"].astype(str).isin(["approved", "promoted"])
    ].copy()


def _overview_payload(
    operators: pd.DataFrame | None,
    accounts: pd.DataFrame | None,
    posts: pd.DataFrame | None,
    families: pd.DataFrame | None,
    patterns: pd.DataFrame | None,
    strategies: pd.DataFrame | None,
    knowledge: pd.DataFrame | None,
    changes: pd.DataFrame | None,
) -> dict[str, Any]:
    active_knowledge = _active_knowledge(knowledge)
    change_count = 0
    if changes is not None and not changes.empty and "is_change_point" in changes.columns:
        change_count = int(changes["is_change_point"].fillna(False).astype(bool).sum())
    knowledge_counts = (
        {
            str(key): int(value)
            for key, value in active_knowledge["knowledge_type"].value_counts().items()
        }
        if not active_knowledge.empty and "knowledge_type" in active_knowledge.columns
        else {}
    )
    status_counts = (
        {
            str(key): int(value)
            for key, value in knowledge["knowledge_status"].value_counts().items()
        }
        if knowledge is not None
        and not knowledge.empty
        and "knowledge_status" in knowledge.columns
        else {}
    )
    return {
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "counts": {
            "operators": int(len(operators)) if operators is not None else 0,
            "accounts": int(len(accounts)) if accounts is not None else 0,
            "posts": int(len(posts)) if posts is not None else 0,
            "families": int(len(families)) if families is not None else 0,
            "patterns": int(len(patterns)) if patterns is not None else 0,
            "strategy_hypotheses": int(len(strategies)) if strategies is not None else 0,
            "knowledge_items": int(len(knowledge)) if knowledge is not None else 0,
            "active_knowledge_items": int(len(active_knowledge)),
            "strategy_change_points": change_count,
        },
        "active_knowledge_by_type": knowledge_counts,
        "knowledge_status_counts": status_counts,
        "operators": _records(operators),
    }


def _accounts_payload(
    accounts: pd.DataFrame | None,
    baselines: pd.DataFrame | None,
    cadence: pd.DataFrame | None,
    role_evidence: pd.DataFrame | None,
    strategies: pd.DataFrame | None,
    knowledge: pd.DataFrame | None,
) -> dict[str, Any]:
    baseline_by_id = _index_rows(baselines, "account_id")
    cadence_by_id = _index_rows(cadence, "account_id")
    role_by_id = _index_rows(role_evidence, "account_id")
    strategy_by_account = _group_rows(strategies, "account_id")
    knowledge_by_account = _group_rows(knowledge, "account_id")
    rows: list[dict[str, Any]] = []
    for account in _records(accounts):
        account_id = str(account.get("account_id") or "")
        rows.append(
            {
                **account,
                "performance_baseline": baseline_by_id.get(account_id),
                "cadence_summary": cadence_by_id.get(account_id),
                "role_evidence": role_by_id.get(account_id),
                "strategy_hypotheses": strategy_by_account.get(account_id, []),
                "knowledge": knowledge_by_account.get(account_id, []),
            }
        )
    return {"accounts": rows}


def _timeline_payload(
    windows: pd.DataFrame | None,
    changes: pd.DataFrame | None,
) -> dict[str, Any]:
    window_rows = _records(windows)
    change_rows = _records(changes)
    return {
        "operator_windows": [
            row for row in window_rows if row.get("scope_type") == "operator"
        ],
        "account_windows": [
            row for row in window_rows if row.get("scope_type") == "account"
        ],
        "change_points": [
            row for row in change_rows if bool(row.get("is_change_point"))
        ],
        "comparisons": change_rows,
    }


def _families_payload(
    families: pd.DataFrame | None,
    members: pd.DataFrame | None,
    propagation: pd.DataFrame | None,
) -> dict[str, Any]:
    members_by_family = _group_rows(members, "family_id")
    propagation_by_family = _group_rows(propagation, "family_id")
    rows: list[dict[str, Any]] = []
    for family in _records(families):
        family_id = str(family.get("family_id") or "")
        rows.append(
            {
                **family,
                "members": members_by_family.get(family_id, []),
                "propagation": propagation_by_family.get(family_id, []),
            }
        )
    return {"families": rows}


def _patterns_payload(
    patterns: pd.DataFrame | None,
    evidence_links: pd.DataFrame | None,
) -> dict[str, Any]:
    links_by_pattern = _group_rows(evidence_links, "pattern_id")
    rows: list[dict[str, Any]] = []
    for pattern in _records(patterns):
        pattern_id = str(pattern.get("pattern_id") or "")
        pattern["metrics"] = _parse_json(pattern.get("metrics_json"), {})
        pattern["counter_evidence"] = _parse_json(
            pattern.get("counter_evidence_json"), {}
        )
        pattern["evidence_links"] = links_by_pattern.get(pattern_id, [])
        rows.append(pattern)
    return {"patterns": rows}


def _strategies_payload(
    strategies: pd.DataFrame | None,
    pattern_links: pd.DataFrame | None,
    evidence_links: pd.DataFrame | None,
) -> dict[str, Any]:
    pattern_by_strategy = _group_rows(pattern_links, "hypothesis_id")
    evidence_by_strategy = _group_rows(evidence_links, "hypothesis_id")
    rows: list[dict[str, Any]] = []
    for strategy in _records(strategies):
        strategy_id = str(strategy.get("hypothesis_id") or "")
        strategy["evidence_summary"] = _parse_json(
            strategy.get("evidence_summary_json"), {}
        )
        strategy["counter_evidence"] = _parse_json(
            strategy.get("counter_evidence_json"), {}
        )
        strategy["alternative_explanations"] = _parse_json(
            strategy.get("alternative_explanations_json"), []
        )
        strategy["pattern_links"] = pattern_by_strategy.get(strategy_id, [])
        strategy["evidence_links"] = evidence_by_strategy.get(strategy_id, [])
        rows.append(strategy)
    return {"strategies": rows}


def _knowledge_payload(
    knowledge: pd.DataFrame | None,
    source_links: pd.DataFrame | None,
    evidence_links: pd.DataFrame | None,
) -> dict[str, Any]:
    source_by_knowledge = _group_rows(source_links, "knowledge_id")
    evidence_by_knowledge = _group_rows(evidence_links, "knowledge_id")
    rows: list[dict[str, Any]] = []
    for item in _records(knowledge):
        knowledge_id = str(item.get("knowledge_id") or "")
        item["payload"] = _parse_json(item.get("payload_json"), {})
        item["exceptions"] = _parse_json(item.get("exceptions_json"), [])
        item["counter_evidence"] = _parse_json(
            item.get("counter_evidence_json"), {}
        )
        item["source_links"] = source_by_knowledge.get(knowledge_id, [])
        item["evidence_links"] = evidence_by_knowledge.get(knowledge_id, [])
        rows.append(item)
    return {
        "knowledge": rows,
        "active": [
            row
            for row in rows
            if row.get("knowledge_status") in {"approved", "promoted"}
        ],
    }


def _sequence_lookup(
    sequence: pd.DataFrame | None,
) -> dict[str, list[dict[str, Any]]]:
    if sequence is None or sequence.empty or "post_uid" not in sequence.columns:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    work = sequence.copy()
    if "position" in work.columns:
        work["_position"] = pd.to_numeric(work["position"], errors="coerce")
        work = work.sort_values(
            ["post_uid", "_position"],
            kind="mergesort",
            na_position="last",
        )
    for post_uid, group in work.groupby("post_uid", sort=False, dropna=True):
        rows = []
        for row in group.to_dict(orient="records"):
            row.pop("_position", None)
            rows.append(_record(row))
        result[str(post_uid)] = rows
    return result


def _evidence_payload(
    posts: pd.DataFrame | None,
    analysis: pd.DataFrame | None,
    performance: pd.DataFrame | None,
    family_members: pd.DataFrame | None,
    sequence: pd.DataFrame | None,
) -> dict[str, Any]:
    analysis_by_post = _index_rows(analysis, "post_uid")
    performance_by_post = _index_rows(performance, "post_uid")
    family_by_post = _index_rows(family_members, "post_uid")
    sequence_by_post = _sequence_lookup(sequence)
    rows: list[dict[str, Any]] = []
    for post in _records(posts):
        post_uid = str(post.get("post_uid") or "")
        creative = analysis_by_post.get(post_uid, {})
        rows.append(
            {
                **post,
                "creative": {
                    key: creative.get(key)
                    for key in (
                        "primary_language_code",
                        "audience_segment",
                        "niche",
                        "topic",
                        "content_angle",
                        "value_type",
                        "pain_point",
                        "desired_outcome",
                        "hook_text",
                        "hook_technique",
                        "hook_psychological_trigger",
                        "hook_replicable_formula",
                        "content_format",
                        "video_format",
                        "narrative_structure",
                        "dominant_visual_type",
                        "visual_aesthetic",
                        "product_family",
                        "product_placement_style",
                        "cta_type",
                        "creative_formula",
                        "overall_confidence",
                    )
                    if key in creative
                },
                "performance": performance_by_post.get(post_uid),
                "family": family_by_post.get(post_uid),
                "sequence": sequence_by_post.get(post_uid, []),
            }
        )
    return {"posts": rows}


def build_workspace_payloads(
    *,
    operators: pd.DataFrame | None = None,
    accounts: pd.DataFrame | None = None,
    posts: pd.DataFrame | None = None,
    creative_analysis: pd.DataFrame | None = None,
    creative_sequence: pd.DataFrame | None = None,
    performance: pd.DataFrame | None = None,
    account_baselines: pd.DataFrame | None = None,
    account_cadence: pd.DataFrame | None = None,
    role_evidence: pd.DataFrame | None = None,
    strategy_windows: pd.DataFrame | None = None,
    strategy_changes: pd.DataFrame | None = None,
    families: pd.DataFrame | None = None,
    family_members: pd.DataFrame | None = None,
    propagation: pd.DataFrame | None = None,
    patterns: pd.DataFrame | None = None,
    pattern_evidence_links: pd.DataFrame | None = None,
    strategies: pd.DataFrame | None = None,
    strategy_pattern_links: pd.DataFrame | None = None,
    strategy_evidence_links: pd.DataFrame | None = None,
    knowledge: pd.DataFrame | None = None,
    knowledge_source_links: pd.DataFrame | None = None,
    knowledge_evidence_links: pd.DataFrame | None = None,
) -> dict[str, Any]:
    return {
        "overview.json": _overview_payload(
            operators,
            accounts,
            posts,
            families,
            patterns,
            strategies,
            knowledge,
            strategy_changes,
        ),
        "accounts.json": _accounts_payload(
            accounts,
            account_baselines,
            account_cadence,
            role_evidence,
            strategies,
            knowledge,
        ),
        "timeline.json": _timeline_payload(strategy_windows, strategy_changes),
        "families.json": _families_payload(
            families,
            family_members,
            propagation,
        ),
        "patterns.json": _patterns_payload(
            patterns,
            pattern_evidence_links,
        ),
        "strategies.json": _strategies_payload(
            strategies,
            strategy_pattern_links,
            strategy_evidence_links,
        ),
        "knowledge.json": _knowledge_payload(
            knowledge,
            knowledge_source_links,
            knowledge_evidence_links,
        ),
        "evidence.json": _evidence_payload(
            posts,
            creative_analysis,
            performance,
            family_members,
            creative_sequence,
        ),
    }


def sync_intelligence_workspace(out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    static_root = resources.files("creative_research").joinpath(
        "intelligence_workspace_static"
    )
    written: list[str] = []
    for name in STATIC_FILES:
        target = out_dir / name
        target.write_bytes(static_root.joinpath(name).read_bytes())
        written.append(name)
    return written


def validate_intelligence_workspace(root: Path) -> list[str]:
    required = (*STATIC_FILES, *REQUIRED_DATA_FILES)
    return [name for name in required if not (root / name).is_file()]


def write_intelligence_workspace(
    *,
    out_dir: Path,
    sources: dict[str, str],
    **frames: pd.DataFrame | None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = build_workspace_payloads(**frames)
    for filename, payload in payloads.items():
        (out_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    manifest = {
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": sources,
        "views": [
            "overview",
            "accounts",
            "timeline",
            "families",
            "patterns",
            "strategies",
            "knowledge",
            "evidence",
        ],
        "counts": payloads["overview.json"]["counts"],
        "notes": [
            "This workspace is a generated research surface, not a new source of truth.",
            "It does not rerun scraping, Vision, analytics, strategy inference, or knowledge promotion.",
            "Knowledge statuses remain visible so review_candidate/rejected/hold items are not confused with active guidance.",
        ],
    }
    (out_dir / "workspace.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    static_files = sync_intelligence_workspace(out_dir)
    return {
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "out": str(out_dir),
        "data_files": len(payloads) + 1,
        "static_files": static_files,
        "counts": manifest["counts"],
    }
