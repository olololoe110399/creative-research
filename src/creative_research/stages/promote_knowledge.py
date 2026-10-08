#!/usr/bin/env python3
"""Promote evidence-backed hypotheses and families into a durable knowledge bank.

Knowledge items are deterministic candidates with explicit status:
- promoted: passed automatic evidence gates;
- review_candidate: useful but should be reviewed before trusted automation;
- approved/rejected/hold: manual review override from optional TOML.

The stage does not call an LLM and preserves lineage to hypotheses, patterns, families,
posts, and accounts.
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
from creative_research.knowledge_reviews import (
    KnowledgeReview,
    load_knowledge_reviews,
)
from creative_research.validation import read_table

KNOWLEDGE_SCHEMA_VERSION = "operator-knowledge-v1"
PROMOTION_METHOD = "deterministic-knowledge-promotion-v1"

KNOWLEDGE_PREFIX = {
    "strategy": "KSTR",
    "rule": "KRUL",
    "lesson": "KLES",
    "template": "KTPL",
    "playbook": "KPLY",
}

PROMOTABLE_STRATEGY_TYPES = {
    "account_origin_exploration",
    "account_reuse_receiver",
    "account_reuse_amplification",
    "operator_explore_propagate_model",
    "selective_cross_account_reuse_model",
    "preserve_core_vary_execution",
    "iterative_reuse_model",
    "performance_responsive_cadence",
    "temporal_strategy_shift",
}

RULE_TYPES = {
    "preserve_core_vary_execution",
    "iterative_reuse_model",
}

LESSON_TYPES = PROMOTABLE_STRATEGY_TYPES


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


def _as_bool(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _parse_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _knowledge_id(
    knowledge_type: str,
    scope_type: str,
    scope_id: str,
    source_key: str,
) -> str:
    prefix = KNOWLEDGE_PREFIX[knowledge_type]
    raw = f"{knowledge_type}\0{scope_type}\0{scope_id}\0{source_key}".encode(
        "utf-8"
    )
    return prefix + "-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def _confidence_band(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"


def _review_for(
    reviews: dict[tuple[str, str], KnowledgeReview],
    source_type: str,
    source_id: str,
) -> KnowledgeReview | None:
    return reviews.get((source_type, source_id))


def _status_from_source(
    *,
    source_type: str,
    source_id: str,
    confidence: float,
    promotion_readiness: str | None,
    reviews: dict[tuple[str, str], KnowledgeReview],
    automatic_threshold: float = 0.76,
) -> tuple[str, KnowledgeReview | None]:
    review = _review_for(reviews, source_type, source_id)
    if review is not None:
        mapping = {
            "approve": "approved",
            "reject": "rejected",
            "hold": "hold",
        }
        return mapping[review.decision], review

    if (
        promotion_readiness == "strong_candidate"
        and confidence >= automatic_threshold
    ):
        return "promoted", None
    return "review_candidate", None


def _base_item(
    *,
    knowledge_type: str,
    subtype: str,
    scope_type: str,
    scope_id: str,
    operator_id: str | None,
    account_id: str | None,
    source_key: str,
    title: str,
    statement: str,
    guidance: str | None,
    confidence: float,
    status: str,
    source_type: str,
    source_ids: list[str],
    pattern_ids: list[str],
    family_ids: list[str],
    exceptions: list[str],
    counter_evidence: dict[str, Any],
    valid_from: str | None,
    valid_to: str | None,
    review: KnowledgeReview | None,
    payload: dict[str, Any],
    review_source_type: str | None = None,
    review_source_id: str | None = None,
) -> dict[str, Any]:
    return {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "knowledge_id": _knowledge_id(
            knowledge_type,
            scope_type,
            scope_id,
            source_key,
        ),
        "knowledge_type": knowledge_type,
        "subtype": subtype,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "operator_id": operator_id,
        "account_id": account_id,
        "title": title,
        "statement": statement,
        "actionable_guidance": guidance,
        "confidence_score": confidence,
        "confidence_band": _confidence_band(confidence),
        "knowledge_status": status,
        "source_type": source_type,
        "source_ids_json": _json(sorted(set(source_ids))),
        "source_pattern_ids_json": _json(sorted(set(pattern_ids))),
        "source_family_ids_json": _json(sorted(set(family_ids))),
        "exceptions_json": _json(exceptions),
        "counter_evidence_json": _json(counter_evidence),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "review_source_type": (
            review_source_type or source_type
        ),
        "review_source_id": (
            review_source_id
            or (
                source_ids[0]
                if len(source_ids) == 1
                else None
            )
        ),
        "review_decision": review.decision if review else None,
        "review_note": review.note if review else None,
        "reviewed_by": review.reviewed_by if review else None,
        "reviewed_at": review.reviewed_at if review else None,
        "payload_json": _json(payload),
        "promotion_method": PROMOTION_METHOD,
    }


def _hypothesis_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "_confidence": _numeric(row.get("confidence_score")) or 0.0,
        "_patterns": [
            str(value)
            for value in _parse_json(
                row.get("supporting_pattern_ids_json"),
                [],
            )
        ],
        "_counter_patterns": [
            str(value)
            for value in _parse_json(
                row.get("counter_pattern_ids_json"),
                [],
            )
        ],
        "_summary": _parse_json(row.get("evidence_summary_json"), {}),
        "_counter": _parse_json(row.get("counter_evidence_json"), {}),
        "_alternatives": [
            str(value)
            for value in _parse_json(
                row.get("alternative_explanations_json"),
                [],
            )
        ],
    }


def _eligible_hypotheses(
    hypotheses: pd.DataFrame,
    *,
    min_confidence: float,
) -> list[dict[str, Any]]:
    if hypotheses.empty:
        return []
    rows: list[dict[str, Any]] = []
    for raw in hypotheses.to_dict(orient="records"):
        row = _hypothesis_record(raw)
        if row["_confidence"] < min_confidence:
            continue
        if _clean(row.get("status")) != "hypothesis":
            continue
        rows.append(row)
    return rows


def _strategy_statement(row: dict[str, Any]) -> tuple[str, str | None]:
    htype = str(row["hypothesis_type"])
    summary = row["_summary"]

    if htype == "account_origin_exploration":
        return (
            "Use this account as a likely concept-origin / exploration surface.",
            "Treat the role as a hypothesis: originate or test concepts here, then validate whether families propagate elsewhere before operationalizing it.",
        )
    if htype in {"account_reuse_receiver", "account_reuse_amplification"}:
        return (
            "Use this account as a likely family-reuse"
            + (
                " / amplification surface."
                if htype == "account_reuse_amplification"
                else " / receiving surface."
            ),
            "Prefer concepts already observed elsewhere in the operator system; compare receiving-account performance and iteration depth rather than assuming automatic scale.",
        )
    if htype == "operator_explore_propagate_model":
        origins = ", ".join(summary.get("origin_accounts", [])) or "origin accounts"
        receivers = ", ".join(summary.get("receiver_accounts", [])) or "receiver accounts"
        return (
            "The operator likely separates concept origination from downstream reuse across accounts.",
            f"Model the system as concept origination on {origins}, followed by reuse/adaptation on {receivers}; keep checking family-level evidence for exceptions.",
        )
    if htype == "selective_cross_account_reuse_model":
        cross_share = summary.get("cross_account_share_of_repeated")
        repeated_rate = summary.get("multi_post_family_rate")
        return (
            "Creative reuse appears selective, but repeated families are usually distributed across multiple verified accounts.",
            (
                "Treat reuse as a selective cross-account propagation behavior rather than assuming every concept is iterated. "
                f"Observed repeated-family rate: {repeated_rate:.1%}; "
                f"cross-account share among repeated families: {cross_share:.1%}."
                if isinstance(repeated_rate, (int, float))
                and isinstance(cross_share, (int, float))
                else
                "Treat reuse as a selective cross-account propagation behavior rather than assuming every concept is iterated."
            ),
        )
    if htype == "preserve_core_vary_execution":
        preserved = ", ".join(summary.get("preserved_core_dimensions", [])) or "core concept"
        changed = ", ".join(summary.get("changed_execution_dimensions", [])) or "execution"
        return (
            "Cross-account reuse likely preserves the core concept while varying execution.",
            f"When adapting a proven family, preserve {preserved}; vary {changed}. Treat this as operator-specific unless validated elsewhere.",
        )
    if htype == "iterative_reuse_model":
        return (
            "The operator likely treats creative as reusable families with multiple executions.",
            "Organize concepts as families, retain lineage across variants, and measure family-level lifecycle instead of treating every post as unrelated.",
        )
    if htype == "performance_responsive_cadence":
        direction = summary.get("direction", "different")
        level = summary.get("level", "operator")
        return (
            f"Posting cadence appears associated with performance at the {level} level.",
            f"Use the observed {direction} post-performance gap relationship as a monitoring signal only; do not automate timing from this correlation without stronger causal evidence.",
        )
    if htype == "temporal_strategy_shift":
        period = summary.get("current_period") or row.get("valid_from")
        return (
            f"A material strategy/content shift is observed around {period}.",
            "Treat knowledge before and after this point as potentially different regimes; avoid applying old-period rules blindly to the new period.",
        )
    return str(row.get("claim") or row.get("title")), None


def _strategy_items(
    hypotheses: list[dict[str, Any]],
    reviews: dict[tuple[str, str], KnowledgeReview],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in hypotheses:
        htype = str(row.get("hypothesis_type"))
        if htype not in PROMOTABLE_STRATEGY_TYPES:
            continue
        hypothesis_id = str(row["hypothesis_id"])
        status, review = _status_from_source(
            source_type="hypothesis",
            source_id=hypothesis_id,
            confidence=row["_confidence"],
            promotion_readiness=_clean(row.get("promotion_readiness")),
            reviews=reviews,
        )
        statement, guidance = _strategy_statement(row)
        rows.append(
            _base_item(
                knowledge_type="strategy",
                subtype=htype,
                scope_type=str(row["scope_type"]),
                scope_id=str(row["scope_id"]),
                operator_id=_clean(row.get("operator_id")),
                account_id=_clean(row.get("account_id")),
                source_key=hypothesis_id,
                title=str(row.get("title") or htype),
                statement=statement,
                guidance=guidance,
                confidence=row["_confidence"],
                status=status,
                source_type="hypothesis",
                source_ids=[hypothesis_id],
                pattern_ids=row["_patterns"],
                family_ids=[],
                exceptions=row["_alternatives"],
                counter_evidence={
                    "direct_counter_patterns": row["_counter_patterns"],
                    "embedded": row["_counter"],
                },
                valid_from=_clean(row.get("valid_from")),
                valid_to=_clean(row.get("valid_to")),
                review=review,
                payload={
                    "original_claim": row.get("claim"),
                    "promotion_readiness": row.get("promotion_readiness"),
                    "evidence_summary": row["_summary"],
                },
            )
        )
    return rows


def _rule_items(
    hypotheses: list[dict[str, Any]],
    reviews: dict[tuple[str, str], KnowledgeReview],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in hypotheses:
        htype = str(row.get("hypothesis_type"))
        if htype not in RULE_TYPES:
            continue
        if row["_confidence"] < 0.68:
            continue
        hypothesis_id = str(row["hypothesis_id"])
        status, review = _status_from_source(
            source_type="hypothesis",
            source_id=hypothesis_id,
            confidence=row["_confidence"],
            promotion_readiness=_clean(row.get("promotion_readiness")),
            reviews=reviews,
            automatic_threshold=0.80,
        )
        summary = row["_summary"]
        if htype == "preserve_core_vary_execution":
            preserved = summary.get("preserved_core_dimensions", [])
            changed = summary.get("changed_execution_dimensions", [])
            statement = (
                "When adapting an observed creative family across this operator's accounts, "
                f"preserve {', '.join(preserved) or 'the core concept'} and vary "
                f"{', '.join(changed) or 'execution details'}."
            )
            title = "Cross-account adaptation rule"
            guidance = (
                "Apply only inside this operator scope unless independently validated in another operator dataset."
            )
        else:
            statement = (
                "Manage recurring concepts as creative families with multiple variants rather "
                "than treating every execution as an unrelated one-off."
            )
            title = "Creative-family iteration rule"
            guidance = (
                "Keep family IDs, origin, variants, lifecycle, and performance lineage when producing or evaluating new executions."
            )

        rows.append(
            _base_item(
                knowledge_type="rule",
                subtype=htype,
                scope_type=str(row["scope_type"]),
                scope_id=str(row["scope_id"]),
                operator_id=_clean(row.get("operator_id")),
                account_id=_clean(row.get("account_id")),
                source_key=hypothesis_id,
                title=title,
                statement=statement,
                guidance=guidance,
                confidence=row["_confidence"],
                status=status,
                source_type="hypothesis",
                source_ids=[hypothesis_id],
                pattern_ids=row["_patterns"],
                family_ids=[],
                exceptions=row["_alternatives"],
                counter_evidence={
                    "direct_counter_patterns": row["_counter_patterns"],
                    "embedded": row["_counter"],
                },
                valid_from=_clean(row.get("valid_from")),
                valid_to=_clean(row.get("valid_to")),
                review=review,
                payload={
                    "evidence_summary": summary,
                    "rule_scope_warning": "operator_specific",
                },
            )
        )
    return rows


def _lesson_items(
    hypotheses: list[dict[str, Any]],
    reviews: dict[tuple[str, str], KnowledgeReview],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in hypotheses:
        htype = str(row.get("hypothesis_type"))
        if htype not in LESSON_TYPES:
            continue
        hypothesis_id = str(row["hypothesis_id"])
        status, review = _status_from_source(
            source_type="hypothesis",
            source_id=hypothesis_id,
            confidence=row["_confidence"],
            promotion_readiness=_clean(row.get("promotion_readiness")),
            reviews=reviews,
            automatic_threshold=0.72,
        )
        statement, _ = _strategy_statement(row)
        rows.append(
            _base_item(
                knowledge_type="lesson",
                subtype=htype,
                scope_type=str(row["scope_type"]),
                scope_id=str(row["scope_id"]),
                operator_id=_clean(row.get("operator_id")),
                account_id=_clean(row.get("account_id")),
                source_key=hypothesis_id,
                title=f"Lesson: {row.get('title')}",
                statement=statement,
                guidance="Use this as a learned observation with its caveats; do not generalize beyond the recorded scope/time without new evidence.",
                confidence=row["_confidence"],
                status=status,
                source_type="hypothesis",
                source_ids=[hypothesis_id],
                pattern_ids=row["_patterns"],
                family_ids=[],
                exceptions=row["_alternatives"],
                counter_evidence={
                    "direct_counter_patterns": row["_counter_patterns"],
                    "embedded": row["_counter"],
                },
                valid_from=_clean(row.get("valid_from")),
                valid_to=_clean(row.get("valid_to")),
                review=review,
                payload={
                    "original_claim": row.get("claim"),
                    "evidence_summary": row["_summary"],
                },
            )
        )
    return rows


def _family_template_score(row: dict[str, Any]) -> float:
    cohesion = _numeric(row.get("anchor_cohesion_mean")) or 0.0
    member_count = max(0, _int(row.get("member_count")))
    account_perf = _numeric(row.get("median_views_percentile_account"))
    max_perf = _numeric(row.get("max_views_percentile_account"))
    performance = account_perf if account_perf is not None else 0.5
    peak = max_perf if max_perf is not None else performance
    count_component = min(1.0, member_count / 6.0)
    return float(
        0.40 * cohesion
        + 0.25 * count_component
        + 0.20 * performance
        + 0.15 * peak
    )


def _template_signature(row: dict[str, Any]) -> str:
    parts = [
        _clean(row.get("operator_id")) or "",
        _clean(row.get("core_angle")) or "",
        _clean(row.get("core_hook_formula")) or "",
        _clean(row.get("core_creative_formula")) or "",
        str(row.get("core_sequence_roles_json") or ""),
    ]
    return "\0".join(parts)


def _template_items(
    families: pd.DataFrame | None,
    members: pd.DataFrame | None,
    reviews: dict[tuple[str, str], KnowledgeReview],
) -> list[dict[str, Any]]:
    if families is None or families.empty:
        return []

    member_lookup: dict[str, list[str]] = {}
    if (
        members is not None
        and not members.empty
        and {"family_id", "post_uid"}.issubset(members.columns)
    ):
        member_lookup = {
            str(family_id): sorted(group["post_uid"].astype(str).tolist())
            for family_id, group in members.groupby("family_id", sort=False)
        }

    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in families.to_dict(orient="records"):
        member_count = _int(row.get("member_count"))
        cohesion = _numeric(row.get("anchor_cohesion_mean"))
        if member_count < 3:
            continue
        if cohesion is not None and cohesion < 0.62:
            continue
        score = _family_template_score(row)
        if score < 0.58:
            continue
        candidates.append((score, row))

    best_by_signature: dict[str, tuple[float, dict[str, Any], list[str]]] = {}
    for score, row in candidates:
        signature = _template_signature(row)
        family_id = str(row["family_id"])
        current = best_by_signature.get(signature)
        if current is None:
            best_by_signature[signature] = (score, row, [family_id])
        else:
            current_score, current_row, family_ids = current
            family_ids = [*family_ids, family_id]
            if score > current_score:
                best_by_signature[signature] = (score, row, family_ids)
            else:
                best_by_signature[signature] = (
                    current_score,
                    current_row,
                    family_ids,
                )

    rows: list[dict[str, Any]] = []
    for signature, (score, row, family_ids) in sorted(best_by_signature.items()):
        family_id = str(row["family_id"])
        review = _review_for(reviews, "family", family_id)
        if review is not None:
            status = {
                "approve": "approved",
                "reject": "rejected",
                "hold": "hold",
            }[review.decision]
        else:
            status = "promoted" if score >= 0.72 and _int(row.get("member_count")) >= 4 else "review_candidate"

        sequence_roles = _parse_json(row.get("core_sequence_roles_json"), [])
        title_bits = [
            _clean(row.get("core_angle")),
            _clean(row.get("core_hook_formula")),
        ]
        title = "Template: " + " / ".join(bit for bit in title_bits if bit)
        if title == "Template: ":
            title = f"Template from {family_id}"

        statement = (
            "Reusable creative-family structure observed across "
            f"{_int(row.get('member_count'))} executions"
            + (
                f" and {_int(row.get('accounts_count'))} accounts."
                if _int(row.get("accounts_count")) > 1
                else "."
            )
        )
        payload = {
            "core_angle": _clean(row.get("core_angle")),
            "core_hook_text": _clean(row.get("core_hook_text")),
            "core_hook_formula": _clean(row.get("core_hook_formula")),
            "core_creative_formula": _clean(row.get("core_creative_formula")),
            "sequence_roles": sequence_roles,
            "origin_account": _clean(row.get("origin_account")),
            "representative_post_uid": _clean(row.get("representative_post_uid")),
            "member_count": _int(row.get("member_count")),
            "variant_count": _int(row.get("variant_count")),
            "accounts_count": _int(row.get("accounts_count")),
            "cross_account": _as_bool(row.get("cross_account", False)),
            "family_confidence": _clean(row.get("family_confidence")),
            "anchor_cohesion_mean": _numeric(row.get("anchor_cohesion_mean")),
            "median_views_percentile_account": _numeric(
                row.get("median_views_percentile_account")
            ),
            "max_views_percentile_account": _numeric(
                row.get("max_views_percentile_account")
            ),
        }
        rows.append(
            _base_item(
                knowledge_type="template",
                subtype="creative_family_structure",
                scope_type="operator",
                scope_id=str(row.get("operator_id") or "unknown"),
                operator_id=_clean(row.get("operator_id")),
                account_id=None,
                source_key=hashlib.sha1(signature.encode("utf-8")).hexdigest(),
                title=title,
                statement=statement,
                guidance=(
                    "Use the sequence/hook/formula as a structural starting point; generate new execution rather than copying source media/text verbatim."
                ),
                confidence=score,
                status=status,
                source_type="family",
                source_ids=family_ids,
                pattern_ids=[],
                family_ids=family_ids,
                exceptions=[
                    "Template quality depends on deterministic family clustering thresholds.",
                    "High historical performance does not guarantee future performance.",
                    "Use as structure, not as permission to copy source creative verbatim.",
                ],
                counter_evidence={
                    "family_cohesion_min": _numeric(row.get("anchor_cohesion_min")),
                },
                valid_from=_clean(row.get("first_seen")),
                valid_to=_clean(row.get("last_seen")),
                review=review,
                payload=payload,
                review_source_type="family",
                review_source_id=family_id,
            )
        )
    return rows


def _adaptation_template_items(
    hypotheses: list[dict[str, Any]],
    reviews: dict[tuple[str, str], KnowledgeReview],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in hypotheses:
        if row.get("hypothesis_type") != "preserve_core_vary_execution":
            continue
        if row["_confidence"] < 0.68:
            continue
        hypothesis_id = str(row["hypothesis_id"])
        status, review = _status_from_source(
            source_type="hypothesis",
            source_id=hypothesis_id,
            confidence=row["_confidence"],
            promotion_readiness=_clean(row.get("promotion_readiness")),
            reviews=reviews,
            automatic_threshold=0.80,
        )
        summary = row["_summary"]
        preserved = summary.get("preserved_core_dimensions", [])
        changed = summary.get("changed_execution_dimensions", [])
        rows.append(
            _base_item(
                knowledge_type="template",
                subtype="cross_account_adaptation",
                scope_type="operator",
                scope_id=str(row["scope_id"]),
                operator_id=_clean(row.get("operator_id")),
                account_id=None,
                source_key=hypothesis_id,
                title="Cross-account creative adaptation template",
                statement=(
                    "Adapt a known creative family by preserving the observed core dimensions "
                    "and varying the execution dimensions."
                ),
                guidance=(
                    f"Preserve: {', '.join(preserved) or 'core concept'}. "
                    f"Vary: {', '.join(changed) or 'execution'}."
                ),
                confidence=row["_confidence"],
                status=status,
                source_type="hypothesis",
                source_ids=[hypothesis_id],
                pattern_ids=row["_patterns"],
                family_ids=[],
                exceptions=row["_alternatives"],
                counter_evidence={
                    "direct_counter_patterns": row["_counter_patterns"],
                    "embedded": row["_counter"],
                },
                valid_from=_clean(row.get("valid_from")),
                valid_to=_clean(row.get("valid_to")),
                review=review,
                payload={
                    "preserve_dimensions": preserved,
                    "vary_dimensions": changed,
                },
            )
        )
    return rows


def _operator_hypothesis_map(
    hypotheses: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in hypotheses:
        operator_id = _clean(row.get("operator_id"))
        if operator_id:
            result.setdefault(operator_id, []).append(row)
    return result


def _playbook_items(
    hypotheses: list[dict[str, Any]],
    reviews: dict[tuple[str, str], KnowledgeReview],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for operator_id, group in sorted(_operator_hypothesis_map(hypotheses).items()):
        by_type = {str(row["hypothesis_type"]): row for row in group}
        required = by_type.get("operator_explore_propagate_model")
        if required is None or required["_confidence"] < 0.65:
            continue

        components = [required]
        for htype in (
            "iterative_reuse_model",
            "preserve_core_vary_execution",
        ):
            candidate = by_type.get(htype)
            if candidate is not None and candidate["_confidence"] >= 0.65:
                components.append(candidate)
        if len(components) < 2:
            continue

        confidence = float(
            sum(row["_confidence"] for row in components) / len(components)
        )
        source_ids = [str(row["hypothesis_id"]) for row in components]
        source_key = "|".join(sorted(source_ids))
        review = _review_for(reviews, "playbook_sources", source_key)
        if review is not None:
            status = {
                "approve": "approved",
                "reject": "rejected",
                "hold": "hold",
            }[review.decision]
        else:
            all_no_counters = all(
                _int(row.get("counter_patterns_count")) == 0
                for row in components
            )
            status = (
                "promoted"
                if confidence >= 0.80 and len(components) >= 3 and all_no_counters
                else "review_candidate"
            )

        model_summary = required["_summary"]
        origin_accounts = model_summary.get("origin_accounts", [])
        receiver_accounts = model_summary.get("receiver_accounts", [])

        steps: list[dict[str, Any]] = [
            {
                "step": 1,
                "action": "Originate or explore candidate concepts on observed origin surfaces.",
                "accounts": origin_accounts,
                "evidence_basis": required["hypothesis_id"],
            },
            {
                "step": 2,
                "action": "Track executions as creative families with stable lineage and relative performance.",
                "accounts": origin_accounts,
                "evidence_basis": (
                    by_type.get("iterative_reuse_model", required)["hypothesis_id"]
                ),
            },
            {
                "step": 3,
                "action": "Propagate selected family concepts to observed receiving/reuse surfaces.",
                "accounts": receiver_accounts,
                "evidence_basis": required["hypothesis_id"],
            },
        ]

        mutation = by_type.get("preserve_core_vary_execution")
        if mutation is not None and mutation["_confidence"] >= 0.65:
            summary = mutation["_summary"]
            steps.append(
                {
                    "step": len(steps) + 1,
                    "action": "Adapt execution while preserving the observed core concept.",
                    "preserve": summary.get("preserved_core_dimensions", []),
                    "vary": summary.get("changed_execution_dimensions", []),
                    "evidence_basis": mutation["hypothesis_id"],
                }
            )

        iteration = by_type.get("iterative_reuse_model")
        if iteration is not None and iteration["_confidence"] >= 0.65:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "action": "Continue iteration at the family level and retain variant/lifecycle evidence.",
                    "evidence_basis": iteration["hypothesis_id"],
                }
            )

        pattern_ids = sorted(
            {
                pattern_id
                for row in components
                for pattern_id in row["_patterns"]
            }
        )
        exceptions = sorted(
            {
                explanation
                for row in components
                for explanation in row["_alternatives"]
            }
        )
        counter = {
            str(row["hypothesis_id"]): {
                "direct_counter_patterns": row["_counter_patterns"],
                "embedded": row["_counter"],
            }
            for row in components
        }

        rows.append(
            _base_item(
                knowledge_type="playbook",
                subtype="explore_propagate_iterate",
                scope_type="operator",
                scope_id=operator_id,
                operator_id=operator_id,
                account_id=None,
                source_key=source_key,
                title="Observed explore → propagate → adapt → iterate playbook",
                statement=(
                    "A reusable operating sequence inferred from the operator's repeated account-flow and family behavior."
                ),
                guidance=(
                    "Use as a baseline operating model for this operator only; validate each step against current-period evidence before automating."
                ),
                confidence=confidence,
                status=status,
                source_type="hypothesis_bundle",
                source_ids=source_ids,
                pattern_ids=pattern_ids,
                family_ids=[],
                exceptions=exceptions,
                counter_evidence=counter,
                valid_from=None,
                valid_to=None,
                review=review,
                review_source_type="playbook_sources",
                review_source_id=source_key,
                payload={
                    "steps": steps,
                    "origin_accounts": origin_accounts,
                    "receiver_accounts": receiver_accounts,
                    "component_hypothesis_types": [
                        row["hypothesis_type"] for row in components
                    ],
                },
            )
        )
    return rows


def _knowledge_source_links(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        source_ids = _parse_json(item["source_ids_json"], [])
        source_type = str(item["source_type"])
        for source_id in source_ids:
            rows.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
                    "knowledge_id": item["knowledge_id"],
                    "knowledge_type": item["knowledge_type"],
                    "source_type": source_type,
                    "source_id": str(source_id),
                    "relation": "derived_from",
                }
            )
    return pd.DataFrame(rows)


def _hypothesis_evidence_lookup(
    strategy_evidence_links: pd.DataFrame | None,
) -> dict[str, list[dict[str, Any]]]:
    if (
        strategy_evidence_links is None
        or strategy_evidence_links.empty
        or "hypothesis_id" not in strategy_evidence_links.columns
    ):
        return {}
    return {
        str(hypothesis_id): group.to_dict(orient="records")
        for hypothesis_id, group in strategy_evidence_links.groupby(
            "hypothesis_id",
            sort=False,
        )
    }


def _family_evidence_lookup(
    family_members: pd.DataFrame | None,
) -> dict[str, list[dict[str, Any]]]:
    if (
        family_members is None
        or family_members.empty
        or not {"family_id", "post_uid"}.issubset(family_members.columns)
    ):
        return {}
    return {
        str(family_id): group.to_dict(orient="records")
        for family_id, group in family_members.groupby("family_id", sort=False)
    }


def _knowledge_evidence_links(
    items: list[dict[str, Any]],
    strategy_evidence_links: pd.DataFrame | None,
    family_members: pd.DataFrame | None,
) -> pd.DataFrame:
    hypothesis_lookup = _hypothesis_evidence_lookup(strategy_evidence_links)
    family_lookup = _family_evidence_lookup(family_members)
    rows: list[dict[str, Any]] = []

    for item in items:
        knowledge_id = str(item["knowledge_id"])
        source_type = str(item["source_type"])
        source_ids = [
            str(value) for value in _parse_json(item["source_ids_json"], [])
        ]

        if source_type in {"hypothesis", "hypothesis_bundle"}:
            for hypothesis_id in source_ids:
                for evidence in hypothesis_lookup.get(hypothesis_id, []):
                    rows.append(
                        {
                            "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                            "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
                            "knowledge_id": knowledge_id,
                            "knowledge_type": item["knowledge_type"],
                            "source_type": "hypothesis",
                            "source_id": hypothesis_id,
                            "pattern_id": _clean(evidence.get("pattern_id")),
                            "relation": _clean(evidence.get("relation")),
                            "post_uid": _clean(evidence.get("post_uid")),
                            "family_id": _clean(evidence.get("family_id")),
                            "account_id": _clean(evidence.get("account_id")),
                            "link_role": _clean(evidence.get("link_role")),
                            "detail": _clean(evidence.get("detail")),
                        }
                    )

        family_ids = [
            str(value)
            for value in _parse_json(item["source_family_ids_json"], [])
        ]
        for family_id in family_ids:
            for member in family_lookup.get(family_id, []):
                rows.append(
                    {
                        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                        "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
                        "knowledge_id": knowledge_id,
                        "knowledge_type": item["knowledge_type"],
                        "source_type": "family",
                        "source_id": family_id,
                        "pattern_id": None,
                        "relation": "template_evidence",
                        "post_uid": _clean(member.get("post_uid")),
                        "family_id": family_id,
                        "account_id": _clean(member.get("account_id")),
                        "link_role": "family_member",
                        "detail": None,
                    }
                )

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.drop_duplicates().sort_values(
            [
                "knowledge_id",
                "source_type",
                "source_id",
                "pattern_id",
                "post_uid",
                "family_id",
            ],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)
    return result


def _write_jsonl(path: Path, frame: pd.DataFrame) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in frame.to_dict(orient="records"):
            handle.write(
                json.dumps(row, ensure_ascii=False, default=str) + "\n"
            )


def build_knowledge_tables(
    hypotheses: pd.DataFrame,
    strategy_evidence_links: pd.DataFrame | None = None,
    families: pd.DataFrame | None = None,
    family_members: pd.DataFrame | None = None,
    *,
    reviews: dict[tuple[str, str], KnowledgeReview] | None = None,
    min_confidence: float = 0.60,
) -> dict[str, pd.DataFrame]:
    required = {
        "hypothesis_id",
        "hypothesis_type",
        "scope_type",
        "scope_id",
        "confidence_score",
        "status",
    }
    missing = sorted(required - set(hypotheses.columns))
    if missing:
        raise ValueError(
            f"strategy_hypotheses table missing required columns: {', '.join(missing)}"
        )
    if hypotheses["hypothesis_id"].duplicated().any():
        raise ValueError(
            "strategy_hypotheses must contain unique hypothesis_id values"
        )

    review_map = reviews or {}
    eligible = _eligible_hypotheses(
        hypotheses,
        min_confidence=min_confidence,
    )

    strategy_items = _strategy_items(eligible, review_map)
    rule_items = _rule_items(eligible, review_map)
    lesson_items = _lesson_items(eligible, review_map)
    template_items = [
        *_template_items(families, family_members, review_map),
        *_adaptation_template_items(eligible, review_map),
    ]
    playbook_items = _playbook_items(eligible, review_map)

    typed_items = {
        "strategies": strategy_items,
        "rules": rule_items,
        "lessons": lesson_items,
        "templates": template_items,
        "playbooks": playbook_items,
    }
    all_items = [
        item
        for name in ("strategies", "rules", "lessons", "templates", "playbooks")
        for item in typed_items[name]
    ]

    tables = {
        name: pd.DataFrame(items)
        for name, items in typed_items.items()
    }
    catalog = pd.DataFrame(all_items)
    if not catalog.empty:
        catalog = catalog.sort_values(
            ["knowledge_type", "scope_type", "scope_id", "knowledge_id"],
            kind="mergesort",
        ).reset_index(drop=True)
    tables["knowledge_catalog"] = catalog
    tables["knowledge_source_links"] = _knowledge_source_links(all_items)
    tables["knowledge_evidence_links"] = _knowledge_evidence_links(
        all_items,
        strategy_evidence_links,
        family_members,
    )
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Promote strategy hypotheses and creative families into a typed, "
            "evidence-linked knowledge bank. No LLM call is performed."
        )
    )
    parser.add_argument(
        "--hypotheses",
        default="data/06_analytics/strategy_hypotheses.parquet",
    )
    parser.add_argument(
        "--strategy-evidence",
        default="data/06_analytics/strategy_evidence_links.parquet",
    )
    parser.add_argument(
        "--families",
        default="data/06_analytics/creative_families.parquet",
    )
    parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    parser.add_argument(
        "--reviews",
        default=None,
        help="Optional local knowledge review TOML.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--out", default="data/07_knowledge")
    args = parser.parse_args()

    paths = {
        "hypotheses": Path(args.hypotheses).expanduser().resolve(),
        "strategy_evidence": Path(args.strategy_evidence).expanduser().resolve(),
        "families": Path(args.families).expanduser().resolve(),
        "family_members": Path(args.family_members).expanduser().resolve(),
    }
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    hypotheses = read_table(paths["hypotheses"])
    strategy_evidence = (
        read_table(paths["strategy_evidence"])
        if paths["strategy_evidence"].exists()
        else None
    )
    families = read_table(paths["families"]) if paths["families"].exists() else None
    family_members = (
        read_table(paths["family_members"])
        if paths["family_members"].exists()
        else None
    )
    reviews_path = (
        Path(args.reviews).expanduser().resolve()
        if args.reviews
        else None
    )
    reviews = load_knowledge_reviews(reviews_path)

    tables = build_knowledge_tables(
        hypotheses,
        strategy_evidence,
        families,
        family_members,
        reviews=reviews,
        min_confidence=args.min_confidence,
    )

    outputs: dict[str, dict[str, str]] = {}
    for name, table in tables.items():
        parquet_path = out_dir / f"{name}.parquet"
        jsonl_path = out_dir / f"{name}.jsonl"
        table.to_parquet(parquet_path, index=False)
        _write_jsonl(jsonl_path, table)
        outputs[name] = {
            "parquet": str(parquet_path),
            "jsonl": str(jsonl_path),
        }

    catalog = tables["knowledge_catalog"]
    status_counts = (
        {
            str(key): int(value)
            for key, value in catalog["knowledge_status"].value_counts().items()
        }
        if "knowledge_status" in catalog.columns
        else {}
    )
    type_counts = (
        {
            str(key): int(value)
            for key, value in catalog["knowledge_type"].value_counts().items()
        }
        if "knowledge_type" in catalog.columns
        else {}
    )
    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "min_confidence": args.min_confidence,
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
    (out_dir / "knowledge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
