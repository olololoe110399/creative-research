"""Source-level review queue calculations; never approve evidence automatically."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

REVIEW_WORKFLOW_SCHEMA_VERSION = "knowledge-review-workflow-v1"

TIER_1_SUBTYPES = {
    "operator_explore_propagate_model",
    "selective_cross_account_reuse_model",
    "account_origin_exploration",
    "account_reuse_receiver",
    "account_reuse_amplification",
}
TIER_2_SUBTYPES = {
    "preserve_core_vary_execution",
    "iterative_reuse_model",
    "performance_responsive_cadence",
    "creative_family_structure",
    "cross_account_adaptation",
    "explore_propagate_iterate",
}

REVIEW_FOCUS = {
    "operator_explore_propagate_model": (
        "Check whether origin/receiver asymmetry is repeated across multiple families "
        "and whether the claim avoids implying formal test→scale intent."
    ),
    "selective_cross_account_reuse_model": (
        "Confirm that reuse is rare overall but predominantly cross-account when it occurs; "
        "check that cross-posting is retained as an alternative explanation."
    ),
    "account_origin_exploration": (
        "Inspect cross-account flow sample size and chronology; confirm this is origin-leaning "
        "evidence, not proof that the account is deliberately used for testing."
    ),
    "account_reuse_receiver": (
        "Inspect imported-family share and sample size; confirm receiving behavior without "
        "upgrading it to scaling/amplification."
    ),
    "account_reuse_amplification": (
        "Require separate repeat/performance evidence in addition to receiving behavior."
    ),
    "preserve_core_vary_execution": (
        "Check actual family examples for preserved core meaning and changed execution; "
        "reject if the claim mainly restates the clustering method."
    ),
    "creative_family_structure": (
        "Inspect every member in the source family and verify the template is reusable structure, "
        "not a broad topic grouping or permission to copy source creative."
    ),
    "temporal_strategy_shift": (
        "Verify the change point is materially different from adjacent windows and consider "
        "seasonality/campaign effects before approving a durable regime claim."
    ),
}


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _json(values: list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=False)


def _review_target(row: dict[str, Any]) -> tuple[str | None, str | None]:
    source_type = str(row.get("review_source_type") or "").strip() or None
    source_id = str(row.get("review_source_id") or "").strip() or None
    if source_type and source_id:
        return source_type, source_id

    source_type = str(row.get("source_type") or "").strip() or None
    source_ids = _parse_json_list(row.get("source_ids_json"))
    if source_type == "hypothesis" and len(source_ids) == 1:
        return "hypothesis", source_ids[0]
    return None, None


def _tier(subtypes: set[str], statuses: set[str]) -> tuple[int, str]:
    if "promoted" in statuses:
        return 1, "audit_auto_promoted"
    if subtypes & TIER_1_SUBTYPES:
        return 1, "operator_or_account_operating_model"
    if "temporal_strategy_shift" in subtypes:
        return 3, "temporal_regime_review"
    if subtypes & TIER_2_SUBTYPES:
        return 2, "behavior_or_template_review"
    return 2, "general_knowledge_review"


def _focus(subtypes: set[str]) -> str:
    ordered = sorted(
        subtypes,
        key=lambda item: (
            0
            if item in TIER_1_SUBTYPES
            else 1
            if item in TIER_2_SUBTYPES
            else 3
            if item == "temporal_strategy_shift"
            else 2,
            item,
        ),
    )
    for subtype in ordered:
        if subtype in REVIEW_FOCUS:
            return REVIEW_FOCUS[subtype]
    return (
        "Check supporting and counter evidence, scope, sample size, and whether the "
        "statement is narrower than the evidence it comes from."
    )


def build_review_queue(
    catalog: pd.DataFrame,
    evidence_links: pd.DataFrame | None = None,
    *,
    include_reviewed: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    if catalog.empty:
        return pd.DataFrame(), {"unresolved_review_targets": 0}

    evidence = evidence_links if evidence_links is not None else pd.DataFrame()
    evidence_by_knowledge: dict[str, pd.DataFrame] = {}
    if not evidence.empty and "knowledge_id" in evidence.columns:
        evidence_by_knowledge = {
            str(key): group for key, group in evidence.groupby("knowledge_id", sort=False)
        }

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    unresolved = 0
    for row in catalog.to_dict(orient="records"):
        status = str(row.get("knowledge_status") or "")
        if not include_reviewed and status not in {"review_candidate", "promoted"}:
            continue
        source_type, source_id = _review_target(row)
        if source_type is None or source_id is None:
            unresolved += 1
            continue
        grouped.setdefault((source_type, source_id), []).append(row)

    rows: list[dict[str, Any]] = []
    for (source_type, source_id), items in grouped.items():
        knowledge_ids = sorted({str(item["knowledge_id"]) for item in items})
        knowledge_types = {str(item.get("knowledge_type") or "") for item in items}
        subtypes = {str(item.get("subtype") or "") for item in items}
        statuses = {str(item.get("knowledge_status") or "") for item in items}
        scope_types = {str(item.get("scope_type") or "") for item in items}
        scope_ids = {str(item.get("scope_id") or "") for item in items}
        confidences = [
            float(value)
            for value in pd.to_numeric(
                pd.Series([item.get("confidence_score") for item in items]),
                errors="coerce",
            )
            .dropna()
            .tolist()
        ]
        pattern_ids: list[str] = []
        family_ids: list[str] = []
        exceptions: list[str] = []
        for item in items:
            pattern_ids.extend(_parse_json_list(item.get("source_pattern_ids_json")))
            family_ids.extend(_parse_json_list(item.get("source_family_ids_json")))
            exceptions.extend(_parse_json_list(item.get("exceptions_json")))

        evidence_frames = [
            evidence_by_knowledge[knowledge_id]
            for knowledge_id in knowledge_ids
            if knowledge_id in evidence_by_knowledge
        ]
        if evidence_frames:
            evidence_group = pd.concat(
                evidence_frames,
                ignore_index=True,
                sort=False,
            ).drop_duplicates()
            evidence_count = int(len(evidence_group))
            post_count = (
                int(evidence_group["post_uid"].dropna().astype(str).nunique())
                if "post_uid" in evidence_group.columns
                else 0
            )
            linked_family_count = (
                int(evidence_group["family_id"].dropna().astype(str).nunique())
                if "family_id" in evidence_group.columns
                else 0
            )
            linked_pattern_count = (
                int(evidence_group["pattern_id"].dropna().astype(str).nunique())
                if "pattern_id" in evidence_group.columns
                else 0
            )
        else:
            evidence_count = 0
            post_count = 0
            linked_family_count = 0
            linked_pattern_count = 0

        tier, priority_reason = _tier(subtypes, statuses)
        representative = sorted(
            items,
            key=lambda item: (
                -float(item.get("confidence_score") or 0.0),
                str(item.get("knowledge_type") or ""),
                str(item.get("knowledge_id") or ""),
            ),
        )[0]

        rows.append(
            {
                "review_workflow_schema_version": REVIEW_WORKFLOW_SCHEMA_VERSION,
                "priority_tier": tier,
                "priority_reason": priority_reason,
                "review_source_type": source_type,
                "review_source_id": source_id,
                "knowledge_statuses_json": _json(list(statuses)),
                "knowledge_ids_json": _json(knowledge_ids),
                "knowledge_types_json": _json(list(knowledge_types)),
                "subtypes_json": _json(list(subtypes)),
                "scope_types_json": _json(list(scope_types)),
                "scope_ids_json": _json(list(scope_ids)),
                "title": str(representative.get("title") or ""),
                "statement": str(representative.get("statement") or ""),
                "confidence_max": max(confidences) if confidences else None,
                "confidence_min": min(confidences) if confidences else None,
                "source_pattern_count": len(set(pattern_ids)),
                "source_family_count": len(set(family_ids)),
                "evidence_link_count": evidence_count,
                "evidence_post_count": post_count,
                "evidence_family_count": linked_family_count,
                "evidence_pattern_count": linked_pattern_count,
                "exceptions_count": len(set(exceptions)),
                "review_focus": _focus(subtypes),
                "existing_review_decision": (representative.get("review_decision")),
                "existing_review_note": representative.get("review_note"),
            }
        )

    queue = pd.DataFrame(rows)
    if not queue.empty:
        queue = queue.sort_values(
            [
                "priority_tier",
                "confidence_max",
                "evidence_link_count",
                "review_source_type",
                "review_source_id",
            ],
            ascending=[True, False, False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
        queue.insert(1, "review_order", range(1, len(queue) + 1))

    return queue, {"unresolved_review_targets": unresolved}
