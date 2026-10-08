#!/usr/bin/env python3
"""Infer evidence-backed strategy hypotheses from deterministic patterns.

This stage is deliberately deterministic. It promotes recurring observations into
reviewable hypotheses with supporting/counter patterns, inherited evidence lineage,
confidence scoring, and alternative explanations.

It does not call an LLM and it does not create final rules/playbooks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.validation import read_table

STRATEGY_SCHEMA_VERSION = "strategy-hypothesis-v1"
INFERENCE_METHOD = "deterministic-evidence-promotion-v1"

STRENGTH_SCORE = {
    "low": 0.35,
    "medium": 0.68,
    "high": 0.90,
}

CORE_PROPAGATION_DIMENSIONS = {
    "topic",
    "content_angle",
    "creative_formula",
    "sequence_roles",
}

EXECUTION_PROPAGATION_DIMENSIONS = {
    "hook_text",
    "hook_technique",
    "format",
    "content_type",
}

ALTERNATIVE_EXPLANATIONS = {
    "account_origin_exploration": [
        "The account may simply be older, larger, or more frequently posted to, making it more likely to contain the earliest observed family.",
        "The observation window may start after an earlier version appeared on another account.",
        "Originating a family does not prove the operator intentionally used the account for testing.",
    ],
    "account_reuse_amplification": [
        "The account may target a different audience, so reuse may reflect adaptation rather than scaling.",
        "Higher receiving-account performance may reflect account baseline or distribution differences rather than deliberate amplification.",
        "Imported families may be cross-posts rather than a formal scaling workflow.",
    ],
    "operator_explore_propagate_model": [
        "Different accounts may have independent editorial roles that accidentally create origin/receiver asymmetry.",
        "Incomplete historical coverage can make one account look like the origin when earlier posts are missing.",
        "Cross-account family reuse does not prove an explicit internal test-then-scale process.",
    ],
    "selective_cross_account_reuse_model": [
        "Cross-account reuse may include routine cross-posting rather than deliberate portfolio-level propagation.",
        "Family clustering thresholds affect which executions count as repeated concepts.",
        "The historical sample may omit deleted or unsampled variants, changing the observed reuse rate.",
    ],
    "preserve_core_vary_execution": [
        "The family clustering method already favors conceptual similarity, so preserved core dimensions are partly expected.",
        "Execution changes may be driven by account format constraints rather than deliberate creative iteration.",
        "Missing/uncertain Vision fields can undercount changes in some dimensions.",
    ],
    "iterative_reuse_model": [
        "Repeated family membership may reflect routine content recycling rather than an intentional iteration system.",
        "Singleton rates depend on family similarity thresholds.",
        "Historical sampling may omit variants that were deleted or not scraped.",
    ],
    "performance_responsive_cadence": [
        "Posting gaps can be explained by preplanned schedules, time of day, or day-of-week effects.",
        "Observed performance is a historical snapshot, not the metric value known to the operator at posting time.",
        "The association does not prove performance caused the next-post timing decision.",
    ],
    "temporal_strategy_shift": [
        "A distribution shift can be seasonal or campaign-driven rather than a durable strategy change.",
        "Changes in account coverage or missing posts can alter window distributions.",
        "A measured shift does not identify the operator's intent without additional evidence.",
    ],
}


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


def _int(value: Any) -> int:
    number = _numeric(value)
    return int(number) if number is not None else 0


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return float(max(lower, min(upper, value)))


def _hypothesis_id(
    hypothesis_type: str,
    scope_type: str,
    scope_id: str,
    key: str,
) -> str:
    raw = f"{hypothesis_type}\0{scope_type}\0{scope_id}\0{key}".encode("utf-8")
    return "STR-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def _confidence_band(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"


def _promotion_readiness(score: float, counter_count: int, support_types: int) -> str:
    if score >= 0.82 and counter_count == 0 and support_types >= 2:
        return "strong_candidate"
    if score >= 0.65:
        return "review"
    return "exploratory"


def _pattern_quality(pattern: dict[str, Any]) -> float:
    strength = STRENGTH_SCORE.get(_clean(pattern.get("evidence_strength")) or "low", 0.35)
    effect = _numeric(pattern.get("effect_size"))
    support_rate = _numeric(pattern.get("support_rate"))
    sample_size = max(0, _int(pattern.get("sample_size")))

    effect_component = (
        min(1.0, abs(effect) / 0.50)
        if effect is not None
        else 0.50
    )
    support_component = support_rate if support_rate is not None else 0.55
    sample_component = min(1.0, math.log10(sample_size + 1) / 2.0)

    return _clamp(
        0.48 * strength
        + 0.22 * effect_component
        + 0.15 * support_component
        + 0.15 * sample_component
    )


def _hypothesis_confidence(
    supports: list[dict[str, Any]],
    counters: list[dict[str, Any]],
    *,
    confidence_cap: float = 0.95,
) -> float:
    if not supports:
        return 0.0
    support_score = sum(_pattern_quality(row) for row in supports) / len(supports)
    pattern_types = {
        _clean(row.get("pattern_type"))
        for row in supports
        if _clean(row.get("pattern_type"))
    }
    diversity_bonus = min(0.12, 0.04 * max(0, len(pattern_types) - 1))

    if counters:
        counter_score = sum(_pattern_quality(row) for row in counters) / len(counters)
        counter_penalty = min(0.28, 0.22 * counter_score + 0.02 * len(counters))
    else:
        counter_penalty = 0.0

    return _clamp(
        support_score + diversity_bonus - counter_penalty,
        upper=confidence_cap,
    )


def _pattern_lookup(patterns: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if patterns.empty or "pattern_id" not in patterns.columns:
        return {}
    return {
        str(row["pattern_id"]): row
        for row in patterns.to_dict(orient="records")
    }


def _pattern_rows(
    patterns: pd.DataFrame,
    *,
    pattern_type: str | None = None,
    operator_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> list[dict[str, Any]]:
    if patterns.empty:
        return []
    work = patterns.copy()
    if pattern_type is not None and "pattern_type" in work.columns:
        work = work.loc[work["pattern_type"].astype(str).eq(pattern_type)]
    if operator_id is not None and "operator_id" in work.columns:
        work = work.loc[work["operator_id"].astype(str).eq(operator_id)]
    if scope_type is not None and "scope_type" in work.columns:
        work = work.loc[work["scope_type"].astype(str).eq(scope_type)]
    if scope_id is not None and "scope_id" in work.columns:
        work = work.loc[work["scope_id"].astype(str).eq(scope_id)]
    return work.to_dict(orient="records")


def _pattern_metrics(pattern: dict[str, Any]) -> dict[str, Any]:
    return _parse_json(pattern.get("metrics_json"))


def _counter_payload(supports: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in supports:
        counter = _parse_json(row.get("counter_evidence_json"))
        if counter:
            payload[str(row.get("pattern_id"))] = counter
    return payload


def _sample_total(patterns: Iterable[dict[str, Any]]) -> int:
    return sum(max(0, _int(row.get("sample_size"))) for row in patterns)


def _make_hypothesis(
    *,
    hypothesis_type: str,
    scope_type: str,
    scope_id: str,
    operator_id: str | None,
    account_id: str | None,
    key: str,
    title: str,
    claim: str,
    supports: list[dict[str, Any]],
    counters: list[dict[str, Any]] | None = None,
    evidence_summary: dict[str, Any] | None = None,
    alternative_explanations: list[str] | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    confidence_cap: float = 0.95,
) -> dict[str, Any]:
    counter_rows = counters or []
    confidence = _hypothesis_confidence(
        supports,
        counter_rows,
        confidence_cap=confidence_cap,
    )
    support_types = {
        str(row.get("pattern_type"))
        for row in supports
        if row.get("pattern_type") is not None
    }
    return {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
        "hypothesis_id": _hypothesis_id(
            hypothesis_type,
            scope_type,
            scope_id,
            key,
        ),
        "hypothesis_type": hypothesis_type,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "operator_id": operator_id,
        "account_id": account_id,
        "title": title,
        "claim": claim,
        "status": "hypothesis",
        "causal_claim": False,
        "confidence_score": confidence,
        "confidence_band": _confidence_band(confidence),
        "evidence_strength": _confidence_band(confidence),
        "promotion_readiness": _promotion_readiness(
            confidence,
            len(counter_rows),
            len(support_types),
        ),
        "supporting_patterns_count": len(supports),
        "counter_patterns_count": len(counter_rows),
        "independent_pattern_types_count": len(support_types),
        "sample_size_total": _sample_total(supports),
        "supporting_pattern_ids_json": _json(
            sorted(str(row["pattern_id"]) for row in supports)
        ),
        "counter_pattern_ids_json": _json(
            sorted(str(row["pattern_id"]) for row in counter_rows)
        ),
        "evidence_summary_json": _json(evidence_summary or {}),
        "counter_evidence_json": _json(_counter_payload(supports)),
        "alternative_explanations_json": _json(
            alternative_explanations
            or ALTERNATIVE_EXPLANATIONS.get(hypothesis_type, [])
        ),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "inference_method": INFERENCE_METHOD,
    }


def _pattern_link_rows(
    hypothesis: dict[str, Any],
    supports: list[dict[str, Any]],
    counters: list[dict[str, Any]],
    *,
    reasons: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    reason_map = reasons or {}
    rows: list[dict[str, Any]] = []
    for relation, patterns in (("support", supports), ("counter", counters)):
        for pattern in patterns:
            pattern_id = str(pattern["pattern_id"])
            rows.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "pattern_id": pattern_id,
                    "relation": relation,
                    "pattern_type": pattern.get("pattern_type"),
                    "pattern_evidence_strength": pattern.get("evidence_strength"),
                    "pattern_quality": _pattern_quality(pattern),
                    "reason": reason_map.get(pattern_id),
                }
            )
    return rows


def _account_role_hypotheses(
    patterns: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    rows = _pattern_rows(
        patterns,
        pattern_type="account_flow_profile",
        scope_type="account",
    )
    for pattern in rows:
        if _clean(pattern.get("evidence_strength")) == "low":
            continue

        metrics = _pattern_metrics(pattern)
        originator = _numeric(metrics.get("originator_signal"))
        receiver = _numeric(metrics.get("receiver_signal"))
        amplifier = _numeric(metrics.get("amplifier_signal"))
        flow_observations = _int(
            metrics.get("cross_account_flow_observations")
        )
        account_id = str(pattern.get("scope_id"))
        operator_id = _clean(pattern.get("operator_id"))
        if originator is None or receiver is None or operator_id is None:
            continue
        if flow_observations and flow_observations < 5:
            continue

        if originator >= 0.65 and originator - receiver >= 0.25:
            family_origin_rate = _numeric(metrics.get("family_origin_rate"))
            outbound_rate = _numeric(metrics.get("outbound_propagation_rate"))
            hypothesis = _make_hypothesis(
                hypothesis_type="account_origin_exploration",
                scope_type="account",
                scope_id=account_id,
                operator_id=operator_id,
                account_id=account_id,
                key="origin-exploration",
                title="Account likely functions as a concept-origin / exploration surface",
                claim=(
                    "This account repeatedly originates creative families that later appear "
                    "elsewhere in the verified operator system, which is consistent with an "
                    "exploration/testing role. Intent is not proven."
                ),
                supports=[pattern],
                evidence_summary={
                    "originator_signal": originator,
                    "receiver_signal": receiver,
                    "family_origin_rate": family_origin_rate,
                    "outbound_propagation_rate": outbound_rate,
                    "cross_account_origin_rate": _numeric(
                        metrics.get("cross_account_origin_rate")
                    ),
                    "cross_account_import_rate": _numeric(
                        metrics.get("cross_account_import_rate")
                    ),
                    "cross_account_flow_observations": _int(
                        metrics.get("cross_account_flow_observations")
                    ),
                },
                confidence_cap=0.82,
            )
            hypotheses.append(hypothesis)
            links.extend(
                _pattern_link_rows(
                    hypothesis,
                    [pattern],
                    [],
                    reasons={
                        str(pattern["pattern_id"]):
                            "Account flow evidence shows repeated family origination and outbound reuse."
                    },
                )
            )

        if receiver >= 0.65 and receiver - originator >= 0.20:
            imported_rate = _numeric(metrics.get("imported_family_rate"))
            hypothesis_type = (
                "account_reuse_amplification"
                if amplifier is not None and amplifier >= 0.55
                else "account_reuse_receiver"
            )
            title = (
                "Account likely functions as a reuse / amplification surface"
                if hypothesis_type == "account_reuse_amplification"
                else "Account likely functions as a family-reuse / receiving surface"
            )
            claim = (
                "This account repeatedly receives creative families first observed elsewhere"
                + (
                    " and shows amplification signals through repeat use and/or receiving-post performance."
                    if hypothesis_type == "account_reuse_amplification"
                    else "."
                )
                + " This is consistent with reuse/scaling behavior, but intent is not proven."
            )
            hypothesis = _make_hypothesis(
                hypothesis_type=hypothesis_type,
                scope_type="account",
                scope_id=account_id,
                operator_id=operator_id,
                account_id=account_id,
                key=hypothesis_type,
                title=title,
                claim=claim,
                supports=[pattern],
                evidence_summary={
                    "originator_signal": originator,
                    "receiver_signal": receiver,
                    "amplifier_signal": amplifier,
                    "imported_family_rate": imported_rate,
                    "cross_account_origin_rate": _numeric(
                        metrics.get("cross_account_origin_rate")
                    ),
                    "cross_account_import_rate": _numeric(
                        metrics.get("cross_account_import_rate")
                    ),
                    "cross_account_flow_observations": _int(
                        metrics.get("cross_account_flow_observations")
                    ),
                },
                alternative_explanations=ALTERNATIVE_EXPLANATIONS[
                    "account_reuse_amplification"
                ],
                confidence_cap=0.82,
            )
            hypotheses.append(hypothesis)
            links.extend(
                _pattern_link_rows(
                    hypothesis,
                    [pattern],
                    [],
                    reasons={
                        str(pattern["pattern_id"]):
                            "Account flow evidence shows repeated imported-family participation."
                    },
                )
            )

    return hypotheses, links


def _family_reuse_pattern(
    patterns: pd.DataFrame,
    operator_id: str,
) -> dict[str, Any] | None:
    rows = _pattern_rows(
        patterns,
        pattern_type="family_reuse_baseline",
        operator_id=operator_id,
    )
    return rows[0] if rows else None


def _operator_explore_propagate_hypotheses(
    patterns: pd.DataFrame,
    account_hypotheses: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    by_operator: dict[str, list[dict[str, Any]]] = {}
    for row in account_hypotheses:
        operator_id = _clean(row.get("operator_id"))
        if operator_id:
            by_operator.setdefault(operator_id, []).append(row)

    pattern_lookup = _pattern_lookup(patterns)

    for operator_id, account_rows in sorted(by_operator.items()):
        origins = [
            row for row in account_rows
            if row["hypothesis_type"] == "account_origin_exploration"
            and row["confidence_score"] >= 0.60
        ]
        receivers = [
            row for row in account_rows
            if row["hypothesis_type"]
            in {"account_reuse_receiver", "account_reuse_amplification"}
            and row["confidence_score"] >= 0.60
        ]
        if not origins or not receivers:
            continue

        support_patterns: list[dict[str, Any]] = []
        account_pattern_ids: set[str] = set()
        for row in [*origins, *receivers]:
            ids = json.loads(row["supporting_pattern_ids_json"])
            account_pattern_ids.update(str(value) for value in ids)
        for pattern_id in sorted(account_pattern_ids):
            if pattern_id in pattern_lookup:
                support_patterns.append(pattern_lookup[pattern_id])

        reuse = _family_reuse_pattern(patterns, operator_id)
        reuse_metrics: dict[str, Any] = {}
        if reuse is not None:
            reuse_metrics = _pattern_metrics(reuse)
            cross_rate = _numeric(
                reuse_metrics.get("cross_account_family_rate")
            )
            conditional_cross_rate = _numeric(
                reuse_metrics.get("cross_account_share_of_repeated")
            )
            if (
                (cross_rate is not None and cross_rate >= 0.20)
                or (
                    conditional_cross_rate is not None
                    and conditional_cross_rate >= 0.70
                )
            ):
                support_patterns.append(reuse)

        if len(support_patterns) < 2:
            continue

        origin_accounts = sorted({row["account_id"] for row in origins})
        receiver_accounts = sorted({row["account_id"] for row in receivers})
        hypothesis = _make_hypothesis(
            hypothesis_type="operator_explore_propagate_model",
            scope_type="operator",
            scope_id=operator_id,
            operator_id=operator_id,
            account_id=None,
            key="explore-propagate",
            title="Operator likely separates concept origination from downstream reuse",
            claim=(
                "Observed account-flow asymmetry is consistent with an operating model where "
                "some accounts originate/explore creative families and other accounts receive, "
                "reuse, or amplify them. This is a strategy hypothesis, not proof of intent."
            ),
            supports=support_patterns,
            evidence_summary={
                "origin_accounts": origin_accounts,
                "receiver_accounts": receiver_accounts,
                "family_reuse_metrics": reuse_metrics,
            },
            confidence_cap=0.92,
        )
        hypotheses.append(hypothesis)
        links.extend(
            _pattern_link_rows(
                hypothesis,
                support_patterns,
                [],
            )
        )

    return hypotheses, links


def _propagation_pattern_map(
    patterns: pd.DataFrame,
    operator_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    rows = _pattern_rows(
        patterns,
        pattern_type="propagation_dimension_behavior",
        operator_id=operator_id,
    )
    for row in rows:
        metrics = _pattern_metrics(row)
        dimension = _clean(metrics.get("dimension"))
        action = _clean(metrics.get("dominant_action"))
        if dimension and action:
            result[(dimension, action)] = row
    return result


def _mutation_hypotheses(
    patterns: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    operator_ids = sorted(
        {
            str(value)
            for value in patterns.loc[
                patterns.get("pattern_type", pd.Series(index=patterns.index, dtype="object"))
                .astype(str)
                .eq("propagation_dimension_behavior"),
                "operator_id",
            ].dropna()
        }
    )

    for operator_id in operator_ids:
        mapping = _propagation_pattern_map(patterns, operator_id)
        support_patterns: list[dict[str, Any]] = []
        counter_patterns: list[dict[str, Any]] = []
        preserved_core: list[str] = []
        changed_execution: list[str] = []

        for dimension in sorted(CORE_PROPAGATION_DIMENSIONS):
            if (dimension, "preserved") in mapping:
                support_patterns.append(mapping[(dimension, "preserved")])
                preserved_core.append(dimension)
            elif (dimension, "changed") in mapping:
                counter_patterns.append(mapping[(dimension, "changed")])

        for dimension in sorted(EXECUTION_PROPAGATION_DIMENSIONS):
            if (dimension, "changed") in mapping:
                support_patterns.append(mapping[(dimension, "changed")])
                changed_execution.append(dimension)
            elif (dimension, "preserved") in mapping:
                counter_patterns.append(mapping[(dimension, "preserved")])

        if not preserved_core or not changed_execution:
            continue
        if len(support_patterns) < 2:
            continue

        hypothesis = _make_hypothesis(
            hypothesis_type="preserve_core_vary_execution",
            scope_type="operator",
            scope_id=operator_id,
            operator_id=operator_id,
            account_id=None,
            key="preserve-core-vary-execution",
            title="Operator likely preserves core concept while varying execution across accounts",
            claim=(
                "During cross-account reuse, core concept/structure dimensions are repeatedly "
                "preserved while execution dimensions such as hook or format are changed. "
                "This is consistent with deliberate adaptation rather than exact duplication."
            ),
            supports=support_patterns,
            counters=counter_patterns,
            evidence_summary={
                "preserved_core_dimensions": preserved_core,
                "changed_execution_dimensions": changed_execution,
            },
            confidence_cap=0.94,
        )
        hypotheses.append(hypothesis)
        links.extend(
            _pattern_link_rows(
                hypothesis,
                support_patterns,
                counter_patterns,
            )
        )

    return hypotheses, links


def _selective_cross_account_reuse_hypotheses(
    patterns: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for pattern in _pattern_rows(
        patterns,
        pattern_type="cross_account_reuse_conditional",
        scope_type="operator",
    ):
        operator_id = _clean(pattern.get("operator_id"))
        if operator_id is None:
            continue

        metrics = _pattern_metrics(pattern)
        repeated_rate = _numeric(metrics.get("multi_post_family_rate"))
        repeated_families = _int(metrics.get("multi_post_families"))
        cross_repeated = _int(
            metrics.get("cross_account_repeated_families")
        )
        cross_share = _numeric(
            metrics.get("cross_account_share_of_repeated")
        )
        if (
            repeated_rate is None
            or cross_share is None
            or repeated_families < 5
            or repeated_rate > 0.25
            or cross_share < 0.70
        ):
            continue

        hypothesis = _make_hypothesis(
            hypothesis_type="selective_cross_account_reuse_model",
            scope_type="operator",
            scope_id=operator_id,
            operator_id=operator_id,
            account_id=None,
            key="selective-cross-account-reuse",
            title="Operator likely uses selective cross-account creative reuse",
            claim=(
                "Most observed creative families are one-offs, but when a family is reused, "
                "the repeated executions usually appear across multiple verified accounts. "
                "This is consistent with selective distributed propagation rather than "
                "high-frequency iteration of every concept."
            ),
            supports=[pattern],
            evidence_summary={
                "multi_post_family_rate": repeated_rate,
                "multi_post_families": repeated_families,
                "cross_account_repeated_families": cross_repeated,
                "cross_account_share_of_repeated": cross_share,
            },
            alternative_explanations=ALTERNATIVE_EXPLANATIONS[
                "selective_cross_account_reuse_model"
            ],
            confidence_cap=0.88,
        )
        hypotheses.append(hypothesis)
        links.extend(_pattern_link_rows(hypothesis, [pattern], []))

    return hypotheses, links


def _iterative_reuse_hypotheses(
    patterns: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for pattern in _pattern_rows(
        patterns,
        pattern_type="family_reuse_baseline",
    ):
        operator_id = _clean(pattern.get("operator_id"))
        if operator_id is None:
            continue
        metrics = _pattern_metrics(pattern)
        multi_rate = _numeric(metrics.get("multi_post_family_rate"))
        cross_rate = _numeric(metrics.get("cross_account_family_rate"))
        lifespan = _numeric(metrics.get("median_family_lifespan_days"))

        if multi_rate is None or multi_rate < 0.50:
            continue

        hypothesis = _make_hypothesis(
            hypothesis_type="iterative_reuse_model",
            scope_type="operator",
            scope_id=operator_id,
            operator_id=operator_id,
            account_id=None,
            key="iterative-reuse",
            title="Operator likely uses repeated creative-family iteration rather than one-off creation",
            claim=(
                "A majority of observed creative families contain multiple executions, "
                "which is consistent with an iterative reuse model. Cross-account reuse, "
                "when present, strengthens the interpretation."
            ),
            supports=[pattern],
            evidence_summary={
                "multi_post_family_rate": multi_rate,
                "cross_account_family_rate": cross_rate,
                "median_family_lifespan_days": lifespan,
            },
            confidence_cap=0.84,
        )
        hypotheses.append(hypothesis)
        links.extend(_pattern_link_rows(hypothesis, [pattern], []))

    return hypotheses, links


def _cadence_hypotheses(
    patterns: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for pattern in _pattern_rows(
        patterns,
        pattern_type="cadence_after_performance",
    ):
        operator_id = _clean(pattern.get("operator_id"))
        if operator_id is None:
            continue
        metrics = _pattern_metrics(pattern)
        effect = _numeric(pattern.get("effect_size"))
        level = _clean(metrics.get("level")) or "operator"
        if effect is None:
            continue
        direction = "longer" if effect > 0 else "shorter"
        hypothesis = _make_hypothesis(
            hypothesis_type="performance_responsive_cadence",
            scope_type="operator",
            scope_id=operator_id,
            operator_id=operator_id,
            account_id=None,
            key=f"{level}:{direction}",
            title=f"Operator cadence appears performance-responsive at {level} level",
            claim=(
                f"High-performing posts are followed by {direction} next-post gaps than "
                "low-performing posts in the observed historical dataset. This is consistent "
                "with performance-responsive cadence, but causation is not established."
            ),
            supports=[pattern],
            evidence_summary={
                "level": level,
                "direction": direction,
                **metrics,
            },
            confidence_cap=0.78,
        )
        hypotheses.append(hypothesis)
        links.extend(_pattern_link_rows(hypothesis, [pattern], []))

    return hypotheses, links


def _temporal_shift_hypotheses(
    patterns: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypotheses: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for pattern in _pattern_rows(
        patterns,
        pattern_type="strategy_change_point",
    ):
        scope_type = _clean(pattern.get("scope_type"))
        scope_id = _clean(pattern.get("scope_id"))
        operator_id = _clean(pattern.get("operator_id"))
        if scope_type is None or scope_id is None:
            continue
        metrics = _pattern_metrics(pattern)
        previous_period = _clean(metrics.get("previous_period"))
        current_period = _clean(metrics.get("current_period"))
        changed_dimensions = metrics.get("changed_dimensions")
        if not isinstance(changed_dimensions, list):
            changed_dimensions = []

        hypothesis = _make_hypothesis(
            hypothesis_type="temporal_strategy_shift",
            scope_type=scope_type,
            scope_id=scope_id,
            operator_id=operator_id,
            account_id=scope_id if scope_type == "account" else None,
            key=f"{previous_period}->{current_period}",
            title=f"Material operating/content shift around {current_period}",
            claim=(
                "The observed content/operating distribution changed materially between "
                f"{previous_period} and {current_period}. This supports a strategy-shift "
                "hypothesis but does not identify the operator's intent."
            ),
            supports=[pattern],
            evidence_summary={
                "previous_period": previous_period,
                "current_period": current_period,
                "changed_dimensions": changed_dimensions,
                "change_score": metrics.get("change_score"),
            },
            valid_from=current_period,
            confidence_cap=0.88,
        )
        hypotheses.append(hypothesis)
        links.extend(_pattern_link_rows(hypothesis, [pattern], []))

    return hypotheses, links


def _dedupe_hypotheses(
    hypotheses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in hypotheses:
        current = by_id.get(str(row["hypothesis_id"]))
        if current is None or float(row["confidence_score"]) > float(current["confidence_score"]):
            by_id[str(row["hypothesis_id"])] = row
    return sorted(
        by_id.values(),
        key=lambda row: (
            str(row["scope_type"]),
            str(row["scope_id"]),
            str(row["hypothesis_type"]),
            str(row["hypothesis_id"]),
        ),
    )


def _inherit_evidence_links(
    hypothesis_pattern_links: pd.DataFrame,
    pattern_evidence_links: pd.DataFrame | None,
) -> pd.DataFrame:
    if (
        pattern_evidence_links is None
        or pattern_evidence_links.empty
        or hypothesis_pattern_links.empty
        or "pattern_id" not in pattern_evidence_links.columns
    ):
        return pd.DataFrame()

    inherited = hypothesis_pattern_links[
        ["hypothesis_id", "pattern_id", "relation"]
    ].merge(
        pattern_evidence_links,
        on="pattern_id",
        how="left",
        suffixes=("", "_pattern"),
    )

    keep = [
        column
        for column in (
            "hypothesis_id",
            "pattern_id",
            "relation",
            "post_uid",
            "family_id",
            "account_id",
            "link_role",
            "detail",
        )
        if column in inherited.columns
    ]
    result = inherited[keep].copy()
    result.insert(0, "strategy_schema_version", STRATEGY_SCHEMA_VERSION)
    result.insert(0, "analytics_schema_version", ANALYTICS_SCHEMA_VERSION)
    if not result.empty:
        result = result.drop_duplicates().sort_values(
            ["hypothesis_id", "relation", "pattern_id", "link_role", "post_uid", "family_id"],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)
    return result


def build_strategy_hypothesis_tables(
    patterns: pd.DataFrame,
    pattern_evidence_links: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    required = {"pattern_id", "pattern_type", "scope_type", "scope_id"}
    missing = sorted(required - set(patterns.columns))
    if missing:
        raise ValueError(f"patterns table missing required columns: {', '.join(missing)}")
    if patterns["pattern_id"].duplicated().any():
        raise ValueError("patterns table must contain unique pattern_id values")

    hypotheses: list[dict[str, Any]] = []
    pattern_links: list[dict[str, Any]] = []

    account_hypotheses, account_links = _account_role_hypotheses(patterns)
    hypotheses.extend(account_hypotheses)
    pattern_links.extend(account_links)

    generators = [
        _operator_explore_propagate_hypotheses(patterns, account_hypotheses),
        _selective_cross_account_reuse_hypotheses(patterns),
        _mutation_hypotheses(patterns),
        _iterative_reuse_hypotheses(patterns),
        _cadence_hypotheses(patterns),
        _temporal_shift_hypotheses(patterns),
    ]
    for generated_hypotheses, generated_links in generators:
        hypotheses.extend(generated_hypotheses)
        pattern_links.extend(generated_links)

    hypotheses = _dedupe_hypotheses(hypotheses)
    hypothesis_ids = {str(row["hypothesis_id"]) for row in hypotheses}
    pattern_links = [
        row for row in pattern_links
        if str(row["hypothesis_id"]) in hypothesis_ids
    ]

    hypotheses_df = pd.DataFrame(hypotheses)
    pattern_links_df = pd.DataFrame(pattern_links)
    if not pattern_links_df.empty:
        pattern_links_df = pattern_links_df.drop_duplicates().sort_values(
            ["hypothesis_id", "relation", "pattern_id"],
            kind="mergesort",
        ).reset_index(drop=True)

    evidence_links_df = _inherit_evidence_links(
        pattern_links_df,
        pattern_evidence_links,
    )

    account_hypotheses_df = (
        hypotheses_df.loc[hypotheses_df["scope_type"].eq("account")].copy()
        if not hypotheses_df.empty and "scope_type" in hypotheses_df.columns
        else pd.DataFrame()
    )
    operator_hypotheses_df = (
        hypotheses_df.loc[hypotheses_df["scope_type"].eq("operator")].copy()
        if not hypotheses_df.empty and "scope_type" in hypotheses_df.columns
        else pd.DataFrame()
    )

    return {
        "strategy_hypotheses": hypotheses_df,
        "account_strategy_hypotheses": account_hypotheses_df,
        "operator_strategy_hypotheses": operator_hypotheses_df,
        "strategy_pattern_links": pattern_links_df,
        "strategy_evidence_links": evidence_links_df,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Promote deterministic evidence patterns into reviewable strategy hypotheses "
            "with supporting/counter evidence. No LLM call is performed."
        )
    )
    parser.add_argument("--patterns", default="data/06_analytics/patterns.parquet")
    parser.add_argument(
        "--pattern-evidence",
        default="data/06_analytics/pattern_evidence_links.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics")
    args = parser.parse_args()

    patterns_path = Path(args.patterns).expanduser().resolve()
    evidence_path = Path(args.pattern_evidence).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    patterns = read_table(patterns_path)
    evidence = read_table(evidence_path) if evidence_path.exists() else None
    tables = build_strategy_hypothesis_tables(patterns, evidence)

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        table.to_parquet(path, index=False)
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
    (out_dir / "strategy_hypotheses_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
