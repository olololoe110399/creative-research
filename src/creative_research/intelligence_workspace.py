from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.operator_product import (
    build_provisional_playbook,
    build_role_flow_index,
    empty_role_lineage,
    hypothesis_trust_status,
    strategy_role_lineage,
)
from creative_research.research_intelligence import build_research_intelligence
from creative_research.reference_media import (
    local_media_sources_for_post,
    preview_media_for_post,
)
from creative_research.stages.review_knowledge import build_review_queue

WORKSPACE_SCHEMA_VERSION = "operator-intelligence-lab-v3"
STATIC_FILES = ("index.html", "app.js", "product_ui.js", "research_ui.js", "style.css", "favicon.svg")
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
    "lab.json",
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
    role_index: dict[str, dict[str, Any]],
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
        role_lineage = strategy_role_lineage(strategy, role_index)
        if role_lineage is not None:
            strategy["flow_evidence"] = role_lineage
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


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    number = _as_float(value)
    return int(number) if number is not None else 0


def _account_network_payload(
    accounts: pd.DataFrame | None,
    role_evidence: pd.DataFrame | None,
    propagation: pd.DataFrame | None,
    strategies: pd.DataFrame | None,
    role_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    role_by_id = _index_rows(role_evidence, "account_id")
    strategy_by_account = _group_rows(strategies, "account_id")
    nodes: list[dict[str, Any]] = []
    for account in _records(accounts):
        account_id = str(account.get("account_id") or "")
        role = role_by_id.get(account_id, {})
        origin = _as_float(role.get("originator_signal")) or 0.0
        receiver = _as_float(role.get("receiver_signal")) or 0.0
        amplifier = _as_float(role.get("amplifier_signal"))
        flow_observations = _as_int(
            role.get("cross_account_flow_observations")
        )
        strength = str(role.get("evidence_strength") or "")
        lineage = role_index.get(account_id, empty_role_lineage())
        if (
            flow_observations >= 5
            and strength != "low"
            and origin >= 0.65
            and origin - receiver >= 0.25
        ):
            role_label = "origin_leaning"
        elif (
            flow_observations >= 5
            and strength != "low"
            and receiver >= 0.65
            and receiver - origin >= 0.20
        ):
            role_label = "receiver_leaning"
        else:
            role_label = "mixed_or_insufficient"
        nodes.append(
            {
                "account_id": account_id,
                "account": account.get("account"),
                "posts": _as_int(account.get("observed_posts")),
                "role_label": role_label,
                "originator_signal": origin,
                "receiver_signal": receiver,
                "amplifier_signal": amplifier,
                "flow_observations": flow_observations,
                "role_lineage": lineage,
                "lineage_matches_summary": (
                    flow_observations == lineage["total_family_observations"]
                ),
                "evidence_strength": role.get("evidence_strength"),
                "strategy_hypotheses": strategy_by_account.get(account_id, []),
            }
        )

    edge_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _records(propagation):
        origin_id = str(row.get("origin_account_id") or "")
        target_id = str(row.get("target_account_id") or "")
        if not origin_id or not target_id:
            continue
        key = (origin_id, target_id)
        edge = edge_map.setdefault(
            key,
            {
                "origin_account_id": origin_id,
                "origin_account": row.get("origin_account"),
                "target_account_id": target_id,
                "target_account": row.get("target_account"),
                "events": 0,
                "families": set(),
                "delays": [],
            },
        )
        edge["events"] += 1
        if row.get("family_id"):
            edge["families"].add(str(row["family_id"]))
        delay = _as_float(row.get("delay_from_family_origin_days"))
        if delay is not None:
            edge["delays"].append(delay)

    edges: list[dict[str, Any]] = []
    for edge in edge_map.values():
        delays = edge.pop("delays")
        families_set = edge.pop("families")
        edges.append(
            {
                **edge,
                "families": len(families_set),
                "family_ids": sorted(families_set),
                "median_delay_days": (
                    float(pd.Series(delays).median()) if delays else None
                ),
            }
        )
    edges.sort(
        key=lambda row: (
            -_as_int(row.get("events")),
            str(row.get("origin_account") or ""),
            str(row.get("target_account") or ""),
        )
    )
    return {"nodes": nodes, "edges": edges}


def _lab_payload(
    operators: pd.DataFrame | None,
    accounts: pd.DataFrame | None,
    posts: pd.DataFrame | None,
    families: pd.DataFrame | None,
    role_evidence: pd.DataFrame | None,
    propagation: pd.DataFrame | None,
    strategies: pd.DataFrame | None,
    knowledge: pd.DataFrame | None,
    knowledge_evidence_links: pd.DataFrame | None,
    role_index: dict[str, dict[str, Any]],
    family_members: pd.DataFrame | None,
    creative_analysis: pd.DataFrame | None,
) -> dict[str, Any]:
    operator_rows = _records(operators)
    operator = operator_rows[0] if operator_rows else {}
    family_rows = _records(families)
    repeated = [
        row for row in family_rows if _as_int(row.get("member_count")) > 1
    ]
    cross_repeated = [
        row for row in repeated if bool(row.get("cross_account"))
    ]
    total_families = len(family_rows)
    repeated_count = len(repeated)
    cross_count = len(cross_repeated)
    repeated_rate = (
        repeated_count / total_families if total_families else None
    )
    cross_share = (
        cross_count / repeated_count if repeated_count else None
    )

    strategy_rows = _records(strategies)
    knowledge_rows = _records(knowledge)
    strategy_by_type: dict[str, list[dict[str, Any]]] = {}
    for row in strategy_rows:
        strategy_by_type.setdefault(
            str(row.get("hypothesis_type") or ""), []
        ).append(row)

    key_order = [
        "selective_cross_account_reuse_model",
        "operator_explore_propagate_model",
        "account_origin_exploration",
        "account_reuse_receiver",
        "preserve_core_vary_execution",
    ]
    key_findings: list[dict[str, Any]] = []
    for hypothesis_type in key_order:
        rows = sorted(
            strategy_by_type.get(hypothesis_type, []),
            key=lambda row: -(
                _as_float(row.get("confidence_score")) or 0.0
            ),
        )
        for row in rows:
            trust_status = hypothesis_trust_status(
                knowledge_rows,
                str(row.get("hypothesis_id") or ""),
                str(operator.get("operator_id") or ""),
            )
            if trust_status in {"hold", "rejected"}:
                continue
            key_findings.append(
                {
                    "trust_status": trust_status,
                    "hypothesis_id": row.get("hypothesis_id"),
                    "hypothesis_type": hypothesis_type,
                    "scope_type": row.get("scope_type"),
                    "scope_id": row.get("scope_id"),
                    "account_id": row.get("account_id"),
                    "title": row.get("title"),
                    "claim": row.get("claim"),
                    "confidence_score": _as_float(
                        row.get("confidence_score")
                    ),
                    "confidence_band": row.get("confidence_band"),
                    "promotion_readiness": row.get(
                        "promotion_readiness"
                    ),
                }
            )

    guardrails = [
        {
            "title": "Observed reuse is not causation",
            "detail": (
                "A later appearance in another account is chronological evidence, "
                "not proof that one account caused another to publish."
            ),
        },
        {
            "title": "Origin / receiver is not internal intent",
            "detail": (
                "Account roles are evidence-backed hypotheses from cross-account "
                "family flow, not proof of a formal testing workflow."
            ),
        },
    ]
    if not strategy_by_type.get("account_reuse_amplification"):
        guardrails.append(
            {
                "title": "No scaling account is proven",
                "detail": (
                    "Receiving a reused family is not enough to call an account "
                    "a scaling or amplification surface."
                ),
            }
        )

    top_families = sorted(
        repeated,
        key=lambda row: (
            -_as_int(row.get("member_count")),
            -_as_int(row.get("accounts_count")),
            str(row.get("family_id") or ""),
        ),
    )[:12]
    family_highlights = [
        {
            "family_id": row.get("family_id"),
            "title": (
                row.get("core_hook_text")
                or row.get("core_angle")
                or "Repeated creative concept"
            ),
            "core_angle": row.get("core_angle"),
            "member_count": _as_int(row.get("member_count")),
            "accounts_count": _as_int(row.get("accounts_count")),
            "cross_account": bool(row.get("cross_account")),
            "origin_account": row.get("origin_account"),
            "languages_count": _as_int(row.get("languages_count")),
            "median_views_percentile_account": _as_float(
                row.get("median_views_percentile_account")
            ),
        }
        for row in top_families
    ]

    review_queue, review_meta = build_review_queue(
        knowledge if knowledge is not None else pd.DataFrame(),
        knowledge_evidence_links,
    )
    review_rows = _records(review_queue)
    all_review_queue, _ = build_review_queue(
        knowledge if knowledge is not None else pd.DataFrame(),
        knowledge_evidence_links,
        include_reviewed=True,
    )
    reviewed_rows = [
        row for row in _records(all_review_queue)
        if row.get("existing_review_decision") in {"approve", "hold", "reject"}
    ]
    tier_counts = (
        {
            str(int(key)): int(value)
            for key, value in review_queue["priority_tier"]
            .value_counts()
            .sort_index()
            .items()
        }
        if not review_queue.empty
        else {}
    )

    hero_strategy = next(
        (
            item
            for item in key_findings
            if item["hypothesis_type"]
            == "selective_cross_account_reuse_model"
        ),
        key_findings[0] if key_findings else None,
    )
    hero = {
        "eyebrow": "Operating model",
        "title": (
            hero_strategy.get("title")
            if hero_strategy
            else "Research model is still forming"
        ),
        "summary": (
            hero_strategy.get("claim")
            if hero_strategy
            else (
                "The evidence base is ready, but no high-value operating-model "
                "hypothesis has been emitted yet."
            )
        ),
        "confidence_score": (
            hero_strategy.get("confidence_score")
            if hero_strategy
            else None
        ),
        "confidence_band": (
            hero_strategy.get("confidence_band")
            if hero_strategy
            else None
        ),
        "trust_status": (
            hero_strategy.get("trust_status") if hero_strategy else "hypothesis_only"
        ),
        "hypothesis_id": (
            hero_strategy.get("hypothesis_id")
            if hero_strategy
            else None
        ),
    }

    playbook_draft = build_provisional_playbook(
        strategy_rows,
        knowledge_rows,
        operator_id=str(operator.get("operator_id") or ""),
    )
    counts = {
        "accounts": int(len(accounts)) if accounts is not None else 0,
        "posts": int(len(posts)) if posts is not None else 0,
        "families": total_families,
        "repeated_families": repeated_count,
        "cross_account_repeated_families": cross_count,
        "repeated_family_rate": repeated_rate,
        "cross_account_share_of_repeated": cross_share,
        "propagation_events": (
            int(len(propagation)) if propagation is not None else 0
        ),
    }
    research_product = build_research_intelligence(
        operator_id=str(operator.get("operator_id") or ""),
        stats=counts,
        strategies=strategy_rows,
        families=family_rows,
        members=_records(family_members),
        posts=_records(posts),
        creative_analysis=_records(creative_analysis),
        playbook_steps=playbook_draft["steps"],
    )
    return {
        "research_intelligence": research_product,
        "research_brief": {
            "operator": {
                "operator_id": operator.get("operator_id"),
                "name": (
                    operator.get("name")
                    or operator.get("operator_id")
                    or "Operator"
                ),
                "verified": bool(operator.get("verified")),
            },
            "hero": hero,
            "stats": counts,
            "key_findings": key_findings,
            "guardrails": guardrails,
        },
        "account_network": _account_network_payload(
            accounts,
            role_evidence,
            propagation,
            strategies,
            role_index,
        ),
        "playbook": playbook_draft,
        "family_highlights": family_highlights,
        "review": {
            "pending_sources": int(len(review_queue)),
            "reviewed_sources": len(reviewed_rows),
            "reviewed_items": reviewed_rows,
            "tier_counts": tier_counts,
            "unresolved_review_targets": review_meta.get(
                "unresolved_review_targets", 0
            ),
            "items": review_rows,
        },
    }


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
        preview = preview_media_for_post(post)
        local_media = local_media_sources_for_post(post)
        if "thumbnail" in local_media:
            preview["thumbnail_url"] = (
                f"/api/media/thumbnail/{post_uid}"
            )
            preview["thumbnail_source"] = "local_archive"
        elif preview.get("thumbnail_url"):
            preview["thumbnail_source"] = "remote_fallback"
        if "video" in local_media:
            preview["video_url"] = f"/api/media/video/{post_uid}"
            preview["video_source"] = "local_archive"
        rows.append(
            {
                **post,
                "preview": preview,
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
    role_index = build_role_flow_index(_records(propagation))
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
            role_index,
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
        "lab.json": _lab_payload(
            operators,
            accounts,
            posts,
            families,
            role_evidence,
            propagation,
            strategies,
            knowledge,
            knowledge_evidence_links,
            role_index,
            family_members,
            creative_analysis,
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
    """Refuse mixed v2/v3 workspaces, not only missing filenames."""
    required = (*STATIC_FILES, *REQUIRED_DATA_FILES)
    issues = [name for name in required if not (root / name).is_file()]
    if "workspace.json" not in issues:
        try:
            manifest = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
            if manifest.get("workspace_schema_version") != WORKSPACE_SCHEMA_VERSION:
                issues.append(
                    f"workspace.json: expected {WORKSPACE_SCHEMA_VERSION} "
                    "(stale export; regenerate the workspace)"
                )
        except (OSError, ValueError, AttributeError):
            issues.append("workspace.json: unreadable manifest")
    if "lab.json" not in issues:
        try:
            lab = json.loads((root / "lab.json").read_text(encoding="utf-8"))
            if not isinstance(lab.get("research_intelligence"), dict):
                issues.append("lab.json: missing Research Intelligence v3")
        except (OSError, ValueError, AttributeError):
            issues.append("lab.json: unreadable research data")
    return issues


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
            "brief",
            "network",
            "families",
            "intelligence",
            "playbook",
            "experiments",
            "advanced",
        ],
        "counts": payloads["overview.json"]["counts"],
        "notes": [
            "This lab is a generated research surface, not a new source of truth.",
            "It does not rerun scraping, Vision, analytics, strategy inference, or knowledge promotion.",
            "Historic knowledge-review statuses are annotations, not a required Research Intelligence approval workflow.",
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
