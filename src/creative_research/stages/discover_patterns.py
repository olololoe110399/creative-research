#!/usr/bin/env python3
"""Discover deterministic evidence patterns from the operator intelligence warehouse.

Patterns are structured observations backed by sample sizes, effect sizes, and stable
post/family/account evidence links. This stage does not create strategy rules or playbooks
and does not call an LLM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.validation import read_table

PATTERN_SCHEMA_VERSION = "evidence-pattern-v1"

PERFORMANCE_DIMENSIONS = (
    "hook_technique",
    "content_angle",
    "format",
    "product_placement_style",
    "cta_type",
    "dominant_visual_type",
    "audience_segment",
)

PROPAGATION_DIMENSIONS = (
    "content_type",
    "topic",
    "content_angle",
    "audience_segment",
    "product_family",
    "hook_technique",
    "format",
    "hook_text",
    "hook_replicable_formula",
    "creative_formula",
    "sequence_roles",
)


def _clean(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "<na>"}:
        return None
    return text


def _numeric(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _median(values: Iterable[Any]) -> float | None:
    clean = [
        number
        for number in (_numeric(value) for value in values)
        if number is not None
    ]
    return float(pd.Series(clean, dtype="float64").median()) if clean else None


def _mean(values: Iterable[Any]) -> float | None:
    clean = [
        number
        for number in (_numeric(value) for value in values)
        if number is not None
    ]
    return float(sum(clean) / len(clean)) if clean else None


def _rate(values: Iterable[bool]) -> float | None:
    items = list(values)
    return float(sum(1 for value in items if value) / len(items)) if items else None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _format_value(record: dict[str, Any]) -> str | None:
    content_format = _clean(record.get("content_format"))
    video_format = _clean(record.get("video_format"))
    return content_format or video_format


def _pattern_id(
    pattern_type: str,
    scope_type: str,
    scope_id: str,
    key: str,
) -> str:
    raw = f"{pattern_type}\0{scope_type}\0{scope_id}\0{key}".encode("utf-8")
    return "PAT-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def _strength(sample_size: int, effect: float | None = None) -> str:
    if sample_size >= 30 and (effect is None or abs(effect) >= 0.15):
        return "high"
    if sample_size >= 10 and (effect is None or abs(effect) >= 0.08):
        return "medium"
    return "low"


def _link(
    pattern_id: str,
    *,
    post_uid: str | None = None,
    family_id: str | None = None,
    account_id: str | None = None,
    link_role: str = "support",
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "pattern_schema_version": PATTERN_SCHEMA_VERSION,
        "pattern_id": pattern_id,
        "post_uid": post_uid,
        "family_id": family_id,
        "account_id": account_id,
        "link_role": link_role,
        "detail": detail,
    }


def _base_record(
    *,
    pattern_id: str,
    pattern_type: str,
    scope_type: str,
    scope_id: str,
    operator_id: str | None,
    title: str,
    observation: str,
    sample_size: int,
    support_count: int | None,
    support_rate: float | None,
    effect_size: float | None,
    metrics: dict[str, Any],
    counter_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "pattern_schema_version": PATTERN_SCHEMA_VERSION,
        "pattern_id": pattern_id,
        "pattern_type": pattern_type,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "operator_id": operator_id,
        "title": title,
        "observation": observation,
        "sample_size": sample_size,
        "support_count": support_count,
        "support_rate": support_rate,
        "effect_size": effect_size,
        "evidence_strength": _strength(sample_size, effect_size),
        "metrics_json": _json(metrics),
        "counter_evidence_json": _json(counter_evidence or {}),
        "causal_claim": False,
    }


def _performance_work(
    analysis: pd.DataFrame,
    performance: pd.DataFrame,
) -> pd.DataFrame:
    cols = [
        column
        for column in (
            "post_uid",
            "operator_id",
            "account_id",
            "account",
            "hook_technique",
            "content_angle",
            "content_format",
            "video_format",
            "product_placement_style",
            "cta_type",
            "dominant_visual_type",
            "audience_segment",
        )
        if column in analysis.columns
    ]
    work = analysis[cols].copy()
    work["format"] = [
        _format_value(record)
        for record in work.to_dict(orient="records")
    ]
    perf_cols = [
        column
        for column in (
            "post_uid",
            "views_percentile_account",
            "views_percentile_operator",
        )
        if column in performance.columns
    ]
    return work.merge(performance[perf_cols], on="post_uid", how="left")


def _dimension_performance_patterns(
    analysis: pd.DataFrame | None,
    performance: pd.DataFrame | None,
    *,
    min_sample: int,
    min_effect: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if (
        analysis is None
        or performance is None
        or analysis.empty
        or performance.empty
        or "post_uid" not in analysis.columns
        or "post_uid" not in performance.columns
    ):
        return [], []

    work = _performance_work(analysis, performance)
    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for operator_id, operator_group in work.loc[
        work["operator_id"].notna()
    ].groupby("operator_id", sort=True):
        baseline = _median(operator_group["views_percentile_account"])
        if baseline is None:
            continue

        for dimension in PERFORMANCE_DIMENSIONS:
            if dimension not in operator_group.columns:
                continue
            values = operator_group[dimension].map(_clean)
            for value in sorted(values.dropna().unique()):
                group = operator_group.loc[values.eq(value)]
                measured = group.loc[
                    pd.to_numeric(
                        group["views_percentile_account"],
                        errors="coerce",
                    ).notna()
                ]
                sample_size = int(len(measured))
                if sample_size < min_sample:
                    continue

                median_perf = _median(measured["views_percentile_account"])
                if median_perf is None:
                    continue
                effect = float(median_perf - baseline)
                top20_rate = _rate(
                    [
                        float(item) >= 0.80
                        for item in pd.to_numeric(
                            measured["views_percentile_account"],
                            errors="coerce",
                        ).dropna()
                    ]
                )
                bottom20_count = int(
                    (
                        pd.to_numeric(
                            measured["views_percentile_account"],
                            errors="coerce",
                        )
                        <= 0.20
                    ).sum()
                )
                if abs(effect) < min_effect:
                    continue

                direction = "above" if effect > 0 else "below"
                key = f"{dimension}:{value}"
                pattern_id = _pattern_id(
                    "creative_dimension_performance",
                    "operator",
                    str(operator_id),
                    key,
                )
                patterns.append(
                    _base_record(
                        pattern_id=pattern_id,
                        pattern_type="creative_dimension_performance",
                        scope_type="operator",
                        scope_id=str(operator_id),
                        operator_id=str(operator_id),
                        title=f"{dimension}={value} performs {direction} operator baseline",
                        observation=(
                            f"Posts with {dimension}={value} have median account-relative "
                            f"views percentile {median_perf:.3f} versus operator baseline "
                            f"{baseline:.3f}."
                        ),
                        sample_size=sample_size,
                        support_count=sample_size - bottom20_count if effect > 0 else bottom20_count,
                        support_rate=top20_rate if effect > 0 else _rate(
                            [
                                float(item) <= 0.20
                                for item in pd.to_numeric(
                                    measured["views_percentile_account"],
                                    errors="coerce",
                                ).dropna()
                            ]
                        ),
                        effect_size=effect,
                        metrics={
                            "dimension": dimension,
                            "value": value,
                            "median_views_percentile_account": median_perf,
                            "operator_baseline_median": baseline,
                            "top20_rate": top20_rate,
                            "bottom20_count": bottom20_count,
                        },
                        counter_evidence={
                            "opposite_extreme_posts": bottom20_count if effect > 0 else int(
                                (
                                    pd.to_numeric(
                                        measured["views_percentile_account"],
                                        errors="coerce",
                                    )
                                    >= 0.80
                                ).sum()
                            )
                        },
                    )
                )
                for post_uid in measured["post_uid"].astype(str):
                    links.append(
                        _link(
                            pattern_id,
                            post_uid=post_uid,
                            link_role="population",
                            detail=f"{dimension}={value}",
                        )
                    )

    return patterns, links


def _cadence_performance_patterns(
    performance: pd.DataFrame | None,
    cadence: pd.DataFrame | None,
    *,
    min_sample: int,
    min_effect: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if (
        performance is None
        or cadence is None
        or performance.empty
        or cadence.empty
        or "post_uid" not in performance.columns
        or "post_uid" not in cadence.columns
    ):
        return [], []

    perf_cols = [
        column
        for column in (
            "post_uid",
            "operator_id",
            "account_id",
            "views_percentile_account",
        )
        if column in performance.columns
    ]
    cadence_cols = [
        column
        for column in (
            "post_uid",
            "gap_to_next_account_hours",
            "gap_to_next_operator_hours",
        )
        if column in cadence.columns
    ]
    work = performance[perf_cols].merge(
        cadence[cadence_cols],
        on="post_uid",
        how="inner",
    )
    view_pct = pd.to_numeric(work["views_percentile_account"], errors="coerce")
    work["_band"] = pd.NA
    work.loc[view_pct.ge(0.80), "_band"] = "high"
    work.loc[view_pct.le(0.20), "_band"] = "low"

    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for operator_id, group in work.loc[
        work["operator_id"].notna()
    ].groupby("operator_id", sort=True):
        for level, gap_col in (
            ("account", "gap_to_next_account_hours"),
            ("operator", "gap_to_next_operator_hours"),
        ):
            if gap_col not in group.columns:
                continue
            high = group.loc[group["_band"].eq("high")]
            low = group.loc[group["_band"].eq("low")]
            high_values = pd.to_numeric(high[gap_col], errors="coerce").dropna()
            low_values = pd.to_numeric(low[gap_col], errors="coerce").dropna()
            if len(high_values) < min_sample or len(low_values) < min_sample:
                continue

            high_median = float(high_values.median())
            low_median = float(low_values.median())
            denominator = max(abs(low_median), 1.0)
            normalized_effect = float((high_median - low_median) / denominator)
            if abs(normalized_effect) < min_effect:
                continue

            direction = "longer" if normalized_effect > 0 else "shorter"
            key = f"{level}:high_vs_low_next_gap"
            pattern_id = _pattern_id(
                "cadence_after_performance",
                "operator",
                str(operator_id),
                key,
            )
            patterns.append(
                _base_record(
                    pattern_id=pattern_id,
                    pattern_type="cadence_after_performance",
                    scope_type="operator",
                    scope_id=str(operator_id),
                    operator_id=str(operator_id),
                    title=f"High performers are followed by {direction} {level} posting gaps",
                    observation=(
                        f"Top-20% posts have median next-{level} gap {high_median:.2f}h "
                        f"versus {low_median:.2f}h after bottom-20% posts."
                    ),
                    sample_size=int(len(high_values) + len(low_values)),
                    support_count=int(len(high_values)),
                    support_rate=None,
                    effect_size=normalized_effect,
                    metrics={
                        "level": level,
                        "high_sample": int(len(high_values)),
                        "low_sample": int(len(low_values)),
                        "high_median_gap_hours": high_median,
                        "low_median_gap_hours": low_median,
                        "normalized_gap_difference": normalized_effect,
                    },
                    counter_evidence={},
                )
            )
            for post_uid in high.loc[high[gap_col].notna(), "post_uid"].astype(str):
                links.append(
                    _link(
                        pattern_id,
                        post_uid=post_uid,
                        link_role="high_performance_cohort",
                    )
                )
            for post_uid in low.loc[low[gap_col].notna(), "post_uid"].astype(str):
                links.append(
                    _link(
                        pattern_id,
                        post_uid=post_uid,
                        link_role="low_performance_cohort",
                    )
                )

    return patterns, links


def _parse_list(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _propagation_dimension_patterns(
    propagation: pd.DataFrame | None,
    *,
    min_sample: int,
    dominant_rate: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if propagation is None or propagation.empty:
        return [], []

    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for operator_id, group in propagation.loc[
        propagation["operator_id"].notna()
    ].groupby("operator_id", sort=True):
        for dimension in PROPAGATION_DIMENSIONS:
            changed: list[bool] = []
            support_rows: list[dict[str, Any]] = []
            counter_rows: list[dict[str, Any]] = []
            for row in group.to_dict(orient="records"):
                changed_dims = set(_parse_list(row.get("changed_dimensions_json")))
                preserved_dims = set(_parse_list(row.get("preserved_dimensions_json")))
                if dimension in changed_dims:
                    changed.append(True)
                    support_rows.append(row)
                elif dimension in preserved_dims:
                    changed.append(False)
                    counter_rows.append(row)
            if len(changed) < min_sample:
                continue

            changed_rate = _rate(changed)
            if changed_rate is None:
                continue
            preserved_rate = 1.0 - changed_rate
            if changed_rate < dominant_rate and preserved_rate < dominant_rate:
                continue

            dominant_action = "changed" if changed_rate >= dominant_rate else "preserved"
            support = support_rows if dominant_action == "changed" else counter_rows
            counter = counter_rows if dominant_action == "changed" else support_rows
            rate = changed_rate if dominant_action == "changed" else preserved_rate
            effect = float(rate - 0.5)

            key = f"{dimension}:{dominant_action}"
            pattern_id = _pattern_id(
                "propagation_dimension_behavior",
                "operator",
                str(operator_id),
                key,
            )
            patterns.append(
                _base_record(
                    pattern_id=pattern_id,
                    pattern_type="propagation_dimension_behavior",
                    scope_type="operator",
                    scope_id=str(operator_id),
                    operator_id=str(operator_id),
                    title=f"{dimension} is usually {dominant_action} during cross-account reuse",
                    observation=(
                        f"{dimension} was {dominant_action} in {len(support)}/{len(changed)} "
                        "observed cross-account family entries."
                    ),
                    sample_size=len(changed),
                    support_count=len(support),
                    support_rate=rate,
                    effect_size=effect,
                    metrics={
                        "dimension": dimension,
                        "dominant_action": dominant_action,
                        "changed_rate": changed_rate,
                        "preserved_rate": preserved_rate,
                    },
                    counter_evidence={"events": len(counter)},
                )
            )
            for row in support:
                links.append(
                    _link(
                        pattern_id,
                        post_uid=_clean(row.get("target_first_post_uid")),
                        family_id=_clean(row.get("family_id")),
                        account_id=_clean(row.get("target_account_id")),
                        link_role="support",
                        detail=dominant_action,
                    )
                )
            for row in counter:
                links.append(
                    _link(
                        pattern_id,
                        post_uid=_clean(row.get("target_first_post_uid")),
                        family_id=_clean(row.get("family_id")),
                        account_id=_clean(row.get("target_account_id")),
                        link_role="counter",
                        detail="counter_example",
                    )
                )

    return patterns, links


def _family_reuse_patterns(
    families: pd.DataFrame | None,
    members: pd.DataFrame | None,
    *,
    min_sample: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if families is None or families.empty or "operator_id" not in families.columns:
        return [], []

    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    member_lookup: dict[str, list[str]] = {}
    if members is not None and not members.empty and {"family_id", "post_uid"}.issubset(members.columns):
        member_lookup = {
            str(family_id): group["post_uid"].astype(str).tolist()
            for family_id, group in members.groupby("family_id", sort=False)
        }

    for operator_id, group in families.loc[
        families["operator_id"].notna()
    ].groupby("operator_id", sort=True):
        sample_size = int(len(group))
        if sample_size < min_sample:
            continue
        cross = group.get("cross_account", pd.Series(False, index=group.index)).fillna(False).astype(bool)
        repeated = pd.to_numeric(
            group.get("member_count", pd.Series(1, index=group.index)),
            errors="coerce",
        ).fillna(1).gt(1)
        cross_rate = float(cross.mean())
        repeated_rate = float(repeated.mean())
        lifespans = pd.to_numeric(
            group.get("lifespan_days", pd.Series(pd.NA, index=group.index)),
            errors="coerce",
        ).dropna()

        pattern_id = _pattern_id(
            "family_reuse_baseline",
            "operator",
            str(operator_id),
            "reuse-baseline",
        )
        patterns.append(
            _base_record(
                pattern_id=pattern_id,
                pattern_type="family_reuse_baseline",
                scope_type="operator",
                scope_id=str(operator_id),
                operator_id=str(operator_id),
                title="Creative-family reuse baseline",
                observation=(
                    f"{repeated_rate:.1%} of observed families have multiple posts and "
                    f"{cross_rate:.1%} appear on multiple verified accounts."
                ),
                sample_size=sample_size,
                support_count=int(repeated.sum()),
                support_rate=repeated_rate,
                effect_size=None,
                metrics={
                    "multi_post_family_rate": repeated_rate,
                    "cross_account_family_rate": cross_rate,
                    "median_family_lifespan_days": (
                        float(lifespans.median()) if not lifespans.empty else None
                    ),
                },
                counter_evidence={
                    "singleton_families": int((~repeated).sum()),
                    "single_account_families": int((~cross).sum()),
                },
            )
        )
        for family_id in group["family_id"].astype(str):
            post_uids = member_lookup.get(family_id, [])
            if post_uids:
                for post_uid in post_uids:
                    links.append(
                        _link(
                            pattern_id,
                            post_uid=post_uid,
                            family_id=family_id,
                            link_role="family_population",
                        )
                    )
            else:
                links.append(
                    _link(
                        pattern_id,
                        family_id=family_id,
                        link_role="family_population",
                    )
                )

    return patterns, links


def _role_evidence_patterns(
    role_evidence: pd.DataFrame | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if role_evidence is None or role_evidence.empty:
        return [], []
    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for row in role_evidence.to_dict(orient="records"):
        profile = _clean(row.get("descriptive_profile"))
        strength = _clean(row.get("evidence_strength"))
        if profile in {None, "insufficient_evidence"} or strength == "low":
            continue
        operator_id = _clean(row.get("operator_id"))
        account_id = _clean(row.get("account_id"))
        if operator_id is None or account_id is None:
            continue
        key = f"{account_id}:{profile}"
        pattern_id = _pattern_id(
            "account_flow_profile",
            "account",
            account_id,
            key,
        )
        observations = int(_numeric(row.get("propagated_origin_families")) or 0) + int(
            _numeric(row.get("imported_families")) or 0
        )
        originator = _numeric(row.get("originator_signal"))
        receiver = _numeric(row.get("receiver_signal"))
        effect = (
            originator - receiver
            if originator is not None and receiver is not None
            else None
        )
        patterns.append(
            {
                **_base_record(
                    pattern_id=pattern_id,
                    pattern_type="account_flow_profile",
                    scope_type="account",
                    scope_id=account_id,
                    operator_id=operator_id,
                    title=f"Account is {profile.replace('_', ' ')} in observed family flow",
                    observation=(
                        f"Observed family-flow profile is {profile}; this is descriptive evidence, "
                        "not a final testing/scaling/conversion role."
                    ),
                    sample_size=max(observations, int(_numeric(row.get("families_participated")) or 0)),
                    support_count=observations,
                    support_rate=None,
                    effect_size=effect,
                    metrics={
                        key: row.get(key)
                        for key in (
                            "family_origin_rate",
                            "imported_family_rate",
                            "outbound_propagation_rate",
                            "cross_account_participation_rate",
                            "originator_signal",
                            "receiver_signal",
                            "amplifier_signal",
                            "evidence_strength",
                        )
                    },
                    counter_evidence={},
                ),
                "evidence_strength": strength,
            }
        )
        links.append(
            _link(
                pattern_id,
                account_id=account_id,
                link_role="account_summary",
                detail=profile,
            )
        )

    return patterns, links


def _strategy_change_patterns(
    changes: pd.DataFrame | None,
    memberships: pd.DataFrame | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if changes is None or changes.empty or "is_change_point" not in changes.columns:
        return [], []

    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    flagged = changes.loc[changes["is_change_point"].fillna(False).astype(bool)]

    for row in flagged.to_dict(orient="records"):
        scope_type = str(row.get("scope_type"))
        scope_id = str(row.get("scope_id"))
        operator_id = _clean(row.get("operator_id"))
        previous_period = str(row.get("previous_period_id"))
        current_period = str(row.get("current_period_id"))
        key = f"{previous_period}->{current_period}"
        pattern_id = _pattern_id(
            "strategy_change_point",
            scope_type,
            scope_id,
            key,
        )
        score = _numeric(row.get("change_score"))
        changed_dimensions = _parse_list(row.get("changed_dimensions_json"))
        patterns.append(
            _base_record(
                pattern_id=pattern_id,
                pattern_type="strategy_change_point",
                scope_type=scope_type,
                scope_id=scope_id,
                operator_id=operator_id,
                title=f"Material strategy-window shift at {current_period}",
                observation=(
                    f"Adjacent-window change score is {score:.3f}; changed dimensions: "
                    + ", ".join(changed_dimensions)
                    if score is not None
                    else "Adjacent-window change point detected."
                ),
                sample_size=int(row.get("previous_posts", 0)) + int(row.get("current_posts", 0)),
                support_count=None,
                support_rate=None,
                effect_size=score,
                metrics={
                    "previous_period": previous_period,
                    "current_period": current_period,
                    "change_score": score,
                    "changed_dimensions": changed_dimensions,
                    "dimension_tvd_json": row.get("dimension_tvd_json"),
                    "scalar_changes_json": row.get("scalar_changes_json"),
                },
                counter_evidence={},
            )
        )

        if memberships is not None and not memberships.empty:
            mask = (
                memberships["scope_type"].astype(str).eq(scope_type)
                & memberships["scope_id"].astype(str).eq(scope_id)
                & memberships["period_id"].astype(str).isin(
                    [previous_period, current_period]
                )
            )
            for evidence in memberships.loc[mask].to_dict(orient="records"):
                links.append(
                    _link(
                        pattern_id,
                        post_uid=_clean(evidence.get("post_uid")),
                        link_role=(
                            "previous_window"
                            if str(evidence.get("period_id")) == previous_period
                            else "current_window"
                        ),
                        detail=str(evidence.get("period_id")),
                    )
                )

    return patterns, links


def build_pattern_tables(
    analysis: pd.DataFrame | None = None,
    performance: pd.DataFrame | None = None,
    cadence: pd.DataFrame | None = None,
    families: pd.DataFrame | None = None,
    family_members: pd.DataFrame | None = None,
    propagation: pd.DataFrame | None = None,
    role_evidence: pd.DataFrame | None = None,
    strategy_changes: pd.DataFrame | None = None,
    strategy_members: pd.DataFrame | None = None,
    *,
    min_sample: int = 5,
    min_performance_effect: float = 0.10,
    min_cadence_effect: float = 0.25,
    propagation_dominant_rate: float = 0.70,
) -> dict[str, pd.DataFrame]:
    patterns: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    builders = [
        _dimension_performance_patterns(
            analysis,
            performance,
            min_sample=min_sample,
            min_effect=min_performance_effect,
        ),
        _cadence_performance_patterns(
            performance,
            cadence,
            min_sample=max(3, min_sample // 2),
            min_effect=min_cadence_effect,
        ),
        _propagation_dimension_patterns(
            propagation,
            min_sample=min_sample,
            dominant_rate=propagation_dominant_rate,
        ),
        _family_reuse_patterns(
            families,
            family_members,
            min_sample=min_sample,
        ),
        _role_evidence_patterns(role_evidence),
        _strategy_change_patterns(strategy_changes, strategy_members),
    ]
    for pattern_rows, link_rows in builders:
        patterns.extend(pattern_rows)
        links.extend(link_rows)

    patterns_df = pd.DataFrame(patterns)
    if not patterns_df.empty:
        patterns_df = patterns_df.sort_values(
            ["pattern_type", "scope_type", "scope_id", "pattern_id"],
            kind="mergesort",
        ).reset_index(drop=True)
    links_df = pd.DataFrame(links)
    if not links_df.empty:
        links_df = links_df.drop_duplicates().sort_values(
            ["pattern_id", "link_role", "post_uid", "family_id"],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)

    return {
        "patterns": patterns_df,
        "pattern_evidence_links": links_df,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover deterministic evidence patterns from canonical analytics. "
            "No LLM call is performed."
        )
    )
    parser.add_argument("--analysis", default="data/05_master/creative_analysis.parquet")
    parser.add_argument("--performance", default="data/06_analytics/post_performance.parquet")
    parser.add_argument("--cadence", default="data/06_analytics/posting_cadence.parquet")
    parser.add_argument("--families", default="data/06_analytics/creative_families.parquet")
    parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    parser.add_argument(
        "--propagation",
        default="data/06_analytics/cross_account_propagation.parquet",
    )
    parser.add_argument(
        "--role-evidence",
        default="data/06_analytics/account_role_evidence.parquet",
    )
    parser.add_argument(
        "--strategy-changes",
        default="data/06_analytics/strategy_change_points.parquet",
    )
    parser.add_argument(
        "--strategy-members",
        default="data/06_analytics/strategy_window_members.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics")
    parser.add_argument("--min-sample", type=int, default=5)
    parser.add_argument("--min-performance-effect", type=float, default=0.10)
    parser.add_argument("--min-cadence-effect", type=float, default=0.25)
    parser.add_argument("--propagation-dominant-rate", type=float, default=0.70)
    args = parser.parse_args()

    paths = {
        "analysis": Path(args.analysis).expanduser().resolve(),
        "performance": Path(args.performance).expanduser().resolve(),
        "cadence": Path(args.cadence).expanduser().resolve(),
        "families": Path(args.families).expanduser().resolve(),
        "family_members": Path(args.family_members).expanduser().resolve(),
        "propagation": Path(args.propagation).expanduser().resolve(),
        "role_evidence": Path(args.role_evidence).expanduser().resolve(),
        "strategy_changes": Path(args.strategy_changes).expanduser().resolve(),
        "strategy_members": Path(args.strategy_members).expanduser().resolve(),
    }

    frames = {
        key: read_table(path) if path.exists() else None
        for key, path in paths.items()
    }
    tables = build_pattern_tables(
        frames["analysis"],
        frames["performance"],
        frames["cadence"],
        frames["families"],
        frames["family_members"],
        frames["propagation"],
        frames["role_evidence"],
        frames["strategy_changes"],
        frames["strategy_members"],
        min_sample=args.min_sample,
        min_performance_effect=args.min_performance_effect,
        min_cadence_effect=args.min_cadence_effect,
        propagation_dominant_rate=args.propagation_dominant_rate,
    )

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        table.to_parquet(path, index=False)
        outputs[name] = str(path)

    patterns = tables["patterns"]
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "pattern_schema_version": PATTERN_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "patterns": int(len(patterns)),
        "pattern_types": (
            {
                str(key): int(value)
                for key, value in patterns["pattern_type"].value_counts().items()
            }
            if "pattern_type" in patterns.columns
            else {}
        ),
        "evidence_links": int(len(tables["pattern_evidence_links"])),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Patterns are structured observations, not rules, playbooks, or causal claims.",
        ],
    }
    (out_dir / "patterns_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
