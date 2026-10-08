#!/usr/bin/env python3
"""Production creative-family v2: calibrated deterministic retrieval + cached AI evidence.

This module deliberately does not call Gemini. It recomputes deterministic candidate
pairs from canonical Vision evidence, preserves the strict v1 family model as a
backward-compatible positive-control layer, applies the reviewed family-v2 gates, and
optionally consumes precomputed AI pair judgments.

The output schema remains compatible with downstream propagation/timeline/pattern stages.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.stages.build_families import (
    DEFAULT_BRIDGE_FLOOR,
    DEFAULT_THRESHOLD,
    FamilyState,
    _build_features,
    _confidence,
    _days_between,
    _family_id,
    _performance_lookup,
    _representative_post_uid,
    _timestamp,
    build_creative_family_tables,
)
from creative_research.stages.calibrate_families import (
    DEFAULT_MAX_PAIRS,
    DEFAULT_MIN_COMBINED,
    DEFAULT_MIN_STRUCTURE,
    calibrate_family_pairs,
)
from creative_research.stages.preview_families_v2 import (
    DEFAULT_BRIDGE_COMBINED,
    DEFAULT_MIN_AI_CONFIDENCE,
    DEFAULT_STRONG_COMBINED,
    build_family_v2_preview,
)

FAMILY_SCHEMA_VERSION_V2 = "creative-family-v2"
FAMILY_MODEL_V2 = "calibrated-hybrid-core-v2"
ACTIVE_AI_SCHEMA_VERSION = "family-ai-judge-v2"
ACTIVE_AI_PROMPT_VERSION = "family-ai-judge-prompt-v2"


def _active_ai_judgments(
    judgments: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, dict[str, int]]:
    if judgments is None or judgments.empty:
        return None, {
            "ai_rows_supplied": 0,
            "ai_rows_active": 0,
            "ai_rows_incompatible": 0,
        }

    work = judgments.copy()
    supplied = int(len(work))
    required = {
        "judge_schema_version",
        "prompt_version",
        "left_post_uid",
        "right_post_uid",
    }
    if not required.issubset(work.columns):
        return None, {
            "ai_rows_supplied": supplied,
            "ai_rows_active": 0,
            "ai_rows_incompatible": supplied,
        }

    mask = (
        work["judge_schema_version"].astype(str).eq(ACTIVE_AI_SCHEMA_VERSION)
        & work["prompt_version"].astype(str).eq(ACTIVE_AI_PROMPT_VERSION)
    )
    active = work.loc[mask].copy()
    if active.empty:
        active_result: pd.DataFrame | None = None
    else:
        active = active.drop_duplicates(
            subset=["left_post_uid", "right_post_uid"],
            keep="last",
        ).reset_index(drop=True)
        active_result = active
    return active_result, {
        "ai_rows_supplied": supplied,
        "ai_rows_active": int(len(active)),
        "ai_rows_incompatible": int((~mask).sum()),
    }


def _match_reason_json(row: dict[str, Any]) -> str:
    anchor_gate = row.get("anchor_gate")
    nearest_gate = row.get("nearest_gate")
    payload = {
        "family_model": FAMILY_MODEL_V2,
        "anchor_score": float(row.get("match_score_to_origin") or 0.0),
        "nearest_score": float(
            row.get("match_score_to_nearest_member") or 0.0
        ),
        "anchor_gate": anchor_gate,
        "nearest_gate": nearest_gate,
        "ai_adjudicated": bool(
            "ai_" in str(anchor_gate or "")
            or "ai_" in str(nearest_gate or "")
        ),
        "strongest_signals": [
            value
            for value in (nearest_gate, anchor_gate)
            if value and value != "origin"
        ][:5],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _materialize_production_tables(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
    preview_members: pd.DataFrame,
    performance: pd.DataFrame | None,
    *,
    strong_combined: float,
    bridge_combined: float,
) -> dict[str, pd.DataFrame]:
    features = _build_features(posts, analysis, sequence)
    feature_lookup = {feature.post_uid: feature for feature in features}
    perf_lookup = _performance_lookup(performance)

    production_family_ids: dict[str, str] = {}
    for preview_family_id, group in preview_members.groupby(
        "family_id",
        sort=False,
    ):
        anchor_uid = str(group["family_origin_post_uid"].iloc[0])
        anchor = feature_lookup[anchor_uid]
        production_family_ids[str(preview_family_id)] = _family_id(
            anchor.operator_scope,
            anchor_uid,
        )

    member_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []

    for preview_family_id, group in preview_members.groupby(
        "family_id",
        sort=False,
    ):
        preview_family_id = str(preview_family_id)
        family_id = production_family_ids[preview_family_id]
        group = group.sort_values(
            ["family_member_index", "post_uid"],
            kind="mergesort",
        )
        anchor_uid = str(group["family_origin_post_uid"].iloc[0])
        anchor = feature_lookup[anchor_uid]

        ordered_features = [
            feature_lookup[str(post_uid)]
            for post_uid in group["post_uid"].astype(str)
        ]
        family_state = FamilyState(
            operator_scope=anchor.operator_scope,
            anchor=anchor,
            members=list(ordered_features),
        )

        first_seen = _timestamp(ordered_features[0].created_at)
        last_seen = _timestamp(ordered_features[-1].created_at)
        account_ids = sorted({item.account_id for item in ordered_features})
        accounts = sorted({item.account for item in ordered_features})
        content_types = sorted(
            {
                item.content_type
                for item in ordered_features
                if item.content_type
            }
        )
        anchor_scores: list[float] = []
        nearest_scores: list[float] = []
        account_percentiles: list[float] = []
        operator_percentiles: list[float] = []
        gate_names: list[str] = []

        group_records = {
            str(row["post_uid"]): row
            for row in group.to_dict(orient="records")
        }

        for index, feature in enumerate(ordered_features, start=1):
            preview_row = group_records[feature.post_uid]
            anchor_score = float(
                preview_row.get("match_score_to_origin") or 0.0
            )
            nearest_score = float(
                preview_row.get("match_score_to_nearest_member") or 0.0
            )
            is_origin = bool(preview_row.get("is_family_origin"))
            if not is_origin:
                anchor_scores.append(anchor_score)
                nearest_scores.append(nearest_score)
                for gate in (
                    preview_row.get("nearest_gate"),
                    preview_row.get("anchor_gate"),
                ):
                    if gate and gate != "origin":
                        gate_names.append(str(gate))

            perf = perf_lookup.get(feature.post_uid, {})
            account_pct = perf.get("views_percentile_account")
            operator_pct = perf.get("views_percentile_operator")
            for value, target in (
                (account_pct, account_percentiles),
                (operator_pct, operator_percentiles),
            ):
                try:
                    if value is not None and not pd.isna(value):
                        target.append(float(value))
                except (TypeError, ValueError):
                    pass

            member_rows.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "family_schema_version": FAMILY_SCHEMA_VERSION_V2,
                    "family_model": FAMILY_MODEL_V2,
                    "family_id": family_id,
                    "operator_id": feature.operator_id,
                    "post_uid": feature.post_uid,
                    "account_id": feature.account_id,
                    "account": feature.account,
                    "post_id": feature.post_id,
                    "created_at": feature.created_at,
                    "content_type": feature.content_type,
                    "family_member_index": index,
                    "is_family_origin": is_origin,
                    "family_origin_post_uid": anchor_uid,
                    "days_since_family_origin": _days_between(
                        anchor.created_at,
                        feature.created_at,
                    ),
                    "match_score_to_origin": anchor_score,
                    "match_score_to_nearest_member": nearest_score,
                    "nearest_member_post_uid": preview_row.get(
                        "nearest_member_post_uid"
                    ),
                    "match_reason_json": _match_reason_json(preview_row),
                    "match_anchor_gate": preview_row.get("anchor_gate"),
                    "match_nearest_gate": preview_row.get("nearest_gate"),
                    "topic": feature.topic,
                    "content_angle": feature.content_angle,
                    "hook_text": feature.hook_text,
                    "hook_replicable_formula": feature.hook_formula,
                    "creative_formula": feature.creative_formula,
                    "sequence_roles_json": json.dumps(
                        list(feature.sequence_roles),
                        ensure_ascii=False,
                    ),
                    "views_percentile_account": account_pct,
                    "views_percentile_operator": operator_pct,
                }
            )

        mean_anchor = (
            float(sum(anchor_scores) / len(anchor_scores))
            if anchor_scores
            else None
        )
        min_anchor = min(anchor_scores) if anchor_scores else None
        mean_nearest = (
            float(sum(nearest_scores) / len(nearest_scores))
            if nearest_scores
            else None
        )
        representative_post_uid = _representative_post_uid(
            family_state,
            perf_lookup,
        )
        ai_gate_count = sum("ai_" in gate for gate in gate_names)

        family_rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "family_schema_version": FAMILY_SCHEMA_VERSION_V2,
                "family_model": FAMILY_MODEL_V2,
                "family_id": family_id,
                "operator_id": anchor.operator_id,
                "family_origin_post_uid": anchor_uid,
                "origin_account_id": anchor.account_id,
                "origin_account": anchor.account,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "lifespan_days": _days_between(
                    ordered_features[0].created_at,
                    ordered_features[-1].created_at,
                ),
                "member_count": len(ordered_features),
                "variant_count": max(0, len(ordered_features) - 1),
                "accounts_count": len(account_ids),
                "cross_account": len(account_ids) > 1,
                "accounts_json": json.dumps(accounts, ensure_ascii=False),
                "content_types_json": json.dumps(
                    content_types,
                    ensure_ascii=False,
                ),
                "representative_post_uid": representative_post_uid,
                "anchor_cohesion_mean": mean_anchor,
                "anchor_cohesion_min": min_anchor,
                "nearest_match_mean": mean_nearest,
                "family_confidence": _confidence(
                    len(ordered_features),
                    mean_anchor,
                ),
                "core_topic": anchor.topic,
                "core_angle": anchor.content_angle,
                "core_hook_text": anchor.hook_text,
                "core_hook_formula": anchor.hook_formula,
                "core_creative_formula": anchor.creative_formula,
                "core_sequence_roles_json": json.dumps(
                    list(anchor.sequence_roles),
                    ensure_ascii=False,
                ),
                "median_views_percentile_account": (
                    float(pd.Series(account_percentiles).median())
                    if account_percentiles
                    else None
                ),
                "max_views_percentile_account": (
                    max(account_percentiles)
                    if account_percentiles
                    else None
                ),
                "median_views_percentile_operator": (
                    float(pd.Series(operator_percentiles).median())
                    if operator_percentiles
                    else None
                ),
                "max_views_percentile_operator": (
                    max(operator_percentiles)
                    if operator_percentiles
                    else None
                ),
                "clustering_threshold": strong_combined,
                "bridge_floor": bridge_combined,
                "clustering_method": FAMILY_MODEL_V2,
                "ai_assisted": ai_gate_count > 0,
                "ai_gate_count": ai_gate_count,
                "match_gates_json": json.dumps(
                    sorted(set(gate_names)),
                    ensure_ascii=False,
                ),
            }
        )

    return {
        "creative_families": pd.DataFrame(family_rows),
        "creative_family_members": pd.DataFrame(member_rows),
    }


def build_creative_family_tables_v2(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
    performance: pd.DataFrame | None = None,
    ai_judgments: pd.DataFrame | None = None,
    *,
    strong_combined: float = DEFAULT_STRONG_COMBINED,
    bridge_combined: float = DEFAULT_BRIDGE_COMBINED,
    min_ai_confidence: float = DEFAULT_MIN_AI_CONFIDENCE,
    calibration_min_structure: float = DEFAULT_MIN_STRUCTURE,
    calibration_min_combined: float = DEFAULT_MIN_COMBINED,
    calibration_max_pairs: int = DEFAULT_MAX_PAIRS,
    legacy_threshold: float = DEFAULT_THRESHOLD,
    legacy_bridge_floor: float = DEFAULT_BRIDGE_FLOOR,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Build production family-v2 tables without making any new AI calls."""

    legacy_stats: dict[str, int] = {}
    legacy_tables = build_creative_family_tables(
        posts,
        analysis,
        sequence,
        performance,
        threshold=legacy_threshold,
        bridge_floor=legacy_bridge_floor,
        clustering_stats=legacy_stats,
    )
    legacy_members = legacy_tables["creative_family_members"][
        ["post_uid", "family_id"]
    ].copy()

    pair_rows, calibration_report = calibrate_family_pairs(
        posts,
        analysis,
        sequence,
        legacy_members,
        min_structure=calibration_min_structure,
        min_combined=calibration_min_combined,
        max_pairs=calibration_max_pairs,
    )

    active_ai, ai_stats = _active_ai_judgments(ai_judgments)
    preview = build_family_v2_preview(
        posts,
        pair_rows,
        analysis,
        active_ai,
        strong_combined=strong_combined,
        bridge_combined=bridge_combined,
        min_ai_confidence=min_ai_confidence,
    )
    preview_members = preview["members"]
    if not isinstance(preview_members, pd.DataFrame):
        raise TypeError("family v2 preview members must be a DataFrame")

    tables = _materialize_production_tables(
        posts,
        analysis,
        sequence,
        preview_members,
        performance,
        strong_combined=strong_combined,
        bridge_combined=bridge_combined,
    )
    preview_report = dict(preview["report"])

    meta = {
        "family_schema_version": FAMILY_SCHEMA_VERSION_V2,
        "family_model": FAMILY_MODEL_V2,
        "strong_combined": strong_combined,
        "bridge_combined": bridge_combined,
        "min_ai_confidence": min_ai_confidence,
        "legacy_v1": {
            "threshold": legacy_threshold,
            "bridge_floor": legacy_bridge_floor,
            "clustering_stats": legacy_stats,
            "families": int(len(legacy_tables["creative_families"])),
            "multi_post_families": int(
                legacy_tables["creative_families"]["member_count"]
                .gt(1)
                .sum()
            ),
        },
        "calibration": calibration_report,
        "ai": ai_stats,
        "preview": preview_report,
    }
    return tables, meta
