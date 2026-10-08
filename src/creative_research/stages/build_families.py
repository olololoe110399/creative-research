#!/usr/bin/env python3
"""Build deterministic creative-family candidates from canonical evidence.

A family represents repeated executions of a likely shared core creative concept inside one
verified operator. This stage does not call an LLM. It compares normalized Vision features and
sequence structure, records why posts were grouped, and keeps every post traceable by post_uid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.validation import read_table

FAMILY_SCHEMA_VERSION = "creative-family-v1"
DEFAULT_THRESHOLD = 0.72
DEFAULT_BRIDGE_FLOOR = 0.52

COMPONENT_WEIGHTS: dict[str, float] = {
    "concept_text": 0.30,
    "hook_text": 0.15,
    "hook_formula": 0.12,
    "creative_formula": 0.10,
    "sequence": 0.13,
    "angle": 0.06,
    "audience": 0.03,
    "product_family": 0.03,
    "format": 0.03,
    "hook_technique": 0.05,
}

TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


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


@lru_cache(maxsize=None)
def _normalize_clean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = [
        token
        for token in TOKEN_RE.findall(normalized)
        if token and not token.isdigit()
    ]
    return " ".join(tokens)


def _normalize_text(value: Any) -> str:
    text = _clean(value)
    return _normalize_clean_text(text) if text else ""


@lru_cache(maxsize=None)
def _tokens_from_normalized(normalized: str) -> frozenset[str]:
    return frozenset(normalized.split()) if normalized else frozenset()


def _tokens(value: Any) -> frozenset[str]:
    return _tokens_from_normalized(_normalize_text(value))


def _text_similarity(left: Any, right: Any) -> float | None:
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text and not right_text:
        return None
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0

    left_tokens = _tokens_from_normalized(left_text)
    right_tokens = _tokens_from_normalized(right_text)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left_text, right_text).ratio()
    return float(0.65 * jaccard + 0.35 * sequence)


def _text_similarity_upper_bound(left: Any, right: Any) -> float | None:
    """Cheap upper bound for _text_similarity without SequenceMatcher.

    SequenceMatcher.ratio() is at most 1, so replacing its contribution with
    0.35 is guaranteed not to under-estimate the real score.
    """
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text and not right_text:
        return None
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0

    left_tokens = _tokens_from_normalized(left_text)
    right_tokens = _tokens_from_normalized(right_text)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return float(0.65 * jaccard + 0.35)


def _exact_similarity(left: Any, right: Any) -> float | None:
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text and not right_text:
        return None
    if not left_text or not right_text:
        return 0.0
    return 1.0 if left_text == right_text else 0.0


def _sequence_similarity(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> float | None:
    if not left and not right:
        return None
    if not left or not right:
        return 0.0
    return float(SequenceMatcher(None, left, right).ratio())


def _concat_text(*values: Any) -> str:
    return " ".join(part for part in (_normalize_text(value) for value in values) if part)


def _format_value(record: dict[str, Any]) -> str | None:
    content_format = _clean(record.get("content_format"))
    video_format = _clean(record.get("video_format"))
    return content_format or video_format


@dataclass(frozen=True, slots=True)
class CreativeFeature:
    post_uid: str
    operator_scope: str
    operator_id: str | None
    account_id: str
    account: str
    post_id: str
    created_at: pd.Timestamp | pd.NaT
    content_type: str | None
    concept_text: str
    hook_text: str | None
    hook_formula: str | None
    creative_formula: str | None
    sequence_roles: tuple[str, ...]
    topic: str | None
    content_angle: str | None
    audience_segment: str | None
    product_family: str | None
    format_value: str | None
    hook_technique: str | None


@dataclass(slots=True)
class FamilyState:
    operator_scope: str
    anchor: CreativeFeature
    members: list[CreativeFeature] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.members:
            self.members.append(self.anchor)


def _family_id(operator_scope: str, anchor_post_uid: str) -> str:
    raw = f"{operator_scope}\0{anchor_post_uid}".encode("utf-8")
    return "FAM-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def _sequence_map(sequence: pd.DataFrame) -> dict[str, tuple[str, ...]]:
    if sequence.empty or "post_uid" not in sequence.columns:
        return {}
    work = sequence.copy()
    if "position" not in work.columns:
        work["position"] = range(1, len(work) + 1)
    work["_position"] = pd.to_numeric(work["position"], errors="coerce")
    work = work.sort_values(["post_uid", "_position"], kind="mergesort")

    result: dict[str, tuple[str, ...]] = {}
    for post_uid, group in work.groupby("post_uid", sort=False, dropna=True):
        roles = tuple(
            role
            for role in (_normalize_text(value) for value in group.get("role", []))
            if role
        )
        result[str(post_uid)] = roles
    return result


def _build_features(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
) -> list[CreativeFeature]:
    required_posts = {
        "post_uid",
        "operator_id",
        "account_id",
        "account",
        "post_id",
        "created_at",
    }
    missing = sorted(required_posts - set(posts.columns))
    if missing:
        raise ValueError(f"posts table missing required columns: {', '.join(missing)}")
    if "post_uid" not in analysis.columns:
        raise ValueError("creative_analysis table missing required column: post_uid")

    if posts["post_uid"].duplicated().any():
        raise ValueError("posts table must contain unique post_uid values")
    if analysis["post_uid"].duplicated().any():
        raise ValueError("creative_analysis table must contain unique post_uid values")

    analysis_records = {
        str(row["post_uid"]): row
        for row in analysis.to_dict(orient="records")
    }
    roles = _sequence_map(sequence)

    features: list[CreativeFeature] = []
    for post in posts.to_dict(orient="records"):
        post_uid = str(post["post_uid"])
        row = {**post, **analysis_records.get(post_uid, {})}
        operator_id = _clean(post.get("operator_id"))
        account_id = str(post.get("account_id") or "")
        operator_scope = operator_id or f"UNMAPPED:{account_id}"
        created_at = pd.to_datetime(post.get("created_at"), errors="coerce", utc=True)

        concept_text = _concat_text(
            row.get("niche"),
            row.get("topic"),
            row.get("pain_point"),
            row.get("desired_outcome"),
        )
        features.append(
            CreativeFeature(
                post_uid=post_uid,
                operator_scope=operator_scope,
                operator_id=operator_id,
                account_id=account_id,
                account=str(post.get("account") or ""),
                post_id=str(post.get("post_id") or ""),
                created_at=created_at,
                content_type=_clean(post.get("content_type")),
                concept_text=concept_text,
                hook_text=_clean(row.get("hook_text")),
                hook_formula=_clean(row.get("hook_replicable_formula")),
                creative_formula=_clean(row.get("creative_formula")),
                sequence_roles=roles.get(post_uid, ()),
                topic=_clean(row.get("topic")),
                content_angle=_clean(row.get("content_angle")),
                audience_segment=_clean(row.get("audience_segment")),
                product_family=_clean(row.get("product_family")),
                format_value=_format_value(row),
                hook_technique=_clean(row.get("hook_technique")),
            )
        )

    def sort_key(item: CreativeFeature) -> tuple[str, int, str]:
        created_ns = (
            int(item.created_at.value)
            if item.created_at is not pd.NaT and not pd.isna(item.created_at)
            else 2**63 - 1
        )
        return item.operator_scope, created_ns, item.post_uid

    return sorted(features, key=sort_key)


def compare_features(
    left: CreativeFeature,
    right: CreativeFeature,
) -> tuple[float, dict[str, float | None]]:
    components: dict[str, float | None] = {
        "concept_text": _text_similarity(left.concept_text, right.concept_text),
        "hook_text": _text_similarity(left.hook_text, right.hook_text),
        "hook_formula": _text_similarity(left.hook_formula, right.hook_formula),
        "creative_formula": _text_similarity(left.creative_formula, right.creative_formula),
        "sequence": _sequence_similarity(left.sequence_roles, right.sequence_roles),
        "angle": _exact_similarity(left.content_angle, right.content_angle),
        "audience": _exact_similarity(left.audience_segment, right.audience_segment),
        "product_family": _exact_similarity(left.product_family, right.product_family),
        "format": _exact_similarity(left.format_value, right.format_value),
        "hook_technique": _exact_similarity(left.hook_technique, right.hook_technique),
    }

    available_weight = sum(
        COMPONENT_WEIGHTS[name]
        for name, value in components.items()
        if value is not None
    )
    if not available_weight:
        return 0.0, components

    score = sum(
        COMPONENT_WEIGHTS[name] * float(value)
        for name, value in components.items()
        if value is not None
    ) / available_weight
    return float(score), components


def compare_features_upper_bound(
    left: CreativeFeature,
    right: CreativeFeature,
) -> float:
    """Return a guaranteed upper bound for compare_features' weighted score."""
    components: dict[str, float | None] = {
        "concept_text": _text_similarity_upper_bound(left.concept_text, right.concept_text),
        "hook_text": _text_similarity_upper_bound(left.hook_text, right.hook_text),
        "hook_formula": _text_similarity_upper_bound(left.hook_formula, right.hook_formula),
        "creative_formula": _text_similarity_upper_bound(
            left.creative_formula,
            right.creative_formula,
        ),
        "sequence": _sequence_similarity(left.sequence_roles, right.sequence_roles),
        "angle": _exact_similarity(left.content_angle, right.content_angle),
        "audience": _exact_similarity(left.audience_segment, right.audience_segment),
        "product_family": _exact_similarity(left.product_family, right.product_family),
        "format": _exact_similarity(left.format_value, right.format_value),
        "hook_technique": _exact_similarity(left.hook_technique, right.hook_technique),
    }
    available_weight = sum(
        COMPONENT_WEIGHTS[name]
        for name, value in components.items()
        if value is not None
    )
    if not available_weight:
        return 0.0
    score = sum(
        COMPONENT_WEIGHTS[name] * float(value)
        for name, value in components.items()
        if value is not None
    ) / available_weight
    return float(score)


def _reason_json(
    components: dict[str, float | None],
    *,
    anchor_score: float,
    nearest_score: float,
) -> str:
    ordered = sorted(
        (
            (name, float(value), COMPONENT_WEIGHTS[name] * float(value))
            for name, value in components.items()
            if value is not None
        ),
        key=lambda item: (-item[2], item[0]),
    )
    payload = {
        "anchor_score": round(anchor_score, 6),
        "nearest_score": round(nearest_score, 6),
        "components": {
            name: round(value, 6)
            for name, value, _ in ordered
        },
        "strongest_signals": [name for name, value, _ in ordered if value >= 0.65][:5],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def cluster_features(
    features: list[CreativeFeature],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    bridge_floor: float = DEFAULT_BRIDGE_FLOOR,
) -> tuple[list[FamilyState], list[dict[str, Any]]]:
    if not 0 <= bridge_floor <= threshold <= 1:
        raise ValueError("Require 0 <= bridge_floor <= threshold <= 1")

    families_by_scope: dict[str, list[FamilyState]] = {}
    assignments: list[dict[str, Any]] = []

    for feature in features:
        scope_families = families_by_scope.setdefault(feature.operator_scope, [])
        best_family: FamilyState | None = None
        best_assignment_score = -1.0
        best_anchor_score = 0.0
        best_nearest_score = 0.0
        best_nearest: CreativeFeature | None = None
        best_components: dict[str, float | None] = {}

        for family in scope_families:
            anchor_score, _ = compare_features(feature, family.anchor)
            nearest_score = -1.0
            nearest: CreativeFeature | None = None
            nearest_components: dict[str, float | None] = {}
            for member in family.members:
                score, components = compare_features(feature, member)
                if score > nearest_score:
                    nearest_score = score
                    nearest = member
                    nearest_components = components

            eligible = (
                anchor_score >= threshold
                or (nearest_score >= threshold and anchor_score >= bridge_floor)
            )
            if not eligible:
                continue

            assignment_score = 0.35 * anchor_score + 0.65 * nearest_score
            if assignment_score > best_assignment_score:
                best_family = family
                best_assignment_score = assignment_score
                best_anchor_score = anchor_score
                best_nearest_score = nearest_score
                best_nearest = nearest
                best_components = nearest_components

        if best_family is None:
            family = FamilyState(operator_scope=feature.operator_scope, anchor=feature)
            scope_families.append(family)
            assignments.append(
                {
                    "feature": feature,
                    "family": family,
                    "anchor_score": 1.0,
                    "nearest_score": 1.0,
                    "nearest_post_uid": feature.post_uid,
                    "match_reason_json": json.dumps(
                        {
                            "anchor_score": 1.0,
                            "nearest_score": 1.0,
                            "components": {},
                            "strongest_signals": ["family_origin"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "is_origin": True,
                }
            )
            continue

        best_family.members.append(feature)
        assignments.append(
            {
                "feature": feature,
                "family": best_family,
                "anchor_score": best_anchor_score,
                "nearest_score": best_nearest_score,
                "nearest_post_uid": (
                    best_nearest.post_uid if best_nearest is not None else best_family.anchor.post_uid
                ),
                "match_reason_json": _reason_json(
                    best_components,
                    anchor_score=best_anchor_score,
                    nearest_score=best_nearest_score,
                ),
                "is_origin": False,
            }
        )

    families = [
        family
        for scope in sorted(families_by_scope)
        for family in families_by_scope[scope]
    ]
    return families, assignments


def _performance_lookup(
    performance: pd.DataFrame | None,
) -> dict[str, dict[str, Any]]:
    if performance is None or performance.empty or "post_uid" not in performance.columns:
        return {}
    return {
        str(row["post_uid"]): row
        for row in performance.to_dict(orient="records")
    }


def _timestamp(value: pd.Timestamp | pd.NaT) -> pd.Timestamp | None:
    if value is pd.NaT or pd.isna(value):
        return None
    return value


def _days_between(
    left: pd.Timestamp | pd.NaT,
    right: pd.Timestamp | pd.NaT,
) -> float | None:
    first = _timestamp(left)
    second = _timestamp(right)
    if first is None or second is None:
        return None
    return float((second - first).total_seconds() / 86400)


def _representative_post_uid(
    family: FamilyState,
    performance_lookup: dict[str, dict[str, Any]],
) -> str:
    scored: list[tuple[float, pd.Timestamp | pd.NaT, str]] = []
    for member in family.members:
        perf = performance_lookup.get(member.post_uid, {})
        raw = perf.get("views_percentile_account")
        try:
            score = float(raw) if raw is not None and not pd.isna(raw) else -1.0
        except (TypeError, ValueError):
            score = -1.0
        scored.append((score, member.created_at, member.post_uid))

    def sort_key(item: tuple[float, pd.Timestamp | pd.NaT, str]) -> tuple[float, int, str]:
        score, created_at, post_uid = item
        created_ns = (
            int(created_at.value)
            if created_at is not pd.NaT and not pd.isna(created_at)
            else 2**63 - 1
        )
        return -score, created_ns, post_uid

    return sorted(scored, key=sort_key)[0][2]


def _confidence(
    member_count: int,
    mean_anchor_score: float | None,
) -> str:
    if member_count <= 1:
        return "singleton"
    if mean_anchor_score is not None and mean_anchor_score >= 0.82:
        return "high"
    if mean_anchor_score is not None and mean_anchor_score >= 0.68:
        return "medium"
    return "low"


def build_creative_family_tables(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
    performance: pd.DataFrame | None = None,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    bridge_floor: float = DEFAULT_BRIDGE_FLOOR,
) -> dict[str, pd.DataFrame]:
    features = _build_features(posts, analysis, sequence)
    families, assignments = cluster_features(
        features,
        threshold=threshold,
        bridge_floor=bridge_floor,
    )
    perf_lookup = _performance_lookup(performance)

    family_id_by_anchor = {
        family.anchor.post_uid: _family_id(
            family.operator_scope,
            family.anchor.post_uid,
        )
        for family in families
    }

    assignment_by_post = {
        item["feature"].post_uid: item
        for item in assignments
    }

    member_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []

    for family in families:
        family_id = family_id_by_anchor[family.anchor.post_uid]
        ordered_members = sorted(
            family.members,
            key=lambda item: (
                (
                    int(item.created_at.value)
                    if item.created_at is not pd.NaT and not pd.isna(item.created_at)
                    else 2**63 - 1
                ),
                item.post_uid,
            ),
        )
        first_seen = _timestamp(ordered_members[0].created_at)
        last_seen = _timestamp(ordered_members[-1].created_at)
        anchor_scores: list[float] = []
        nearest_scores: list[float] = []
        account_ids = sorted({member.account_id for member in ordered_members})
        accounts = sorted({member.account for member in ordered_members})
        content_types = sorted(
            {member.content_type for member in ordered_members if member.content_type}
        )

        account_percentiles: list[float] = []
        operator_percentiles: list[float] = []

        for index, member in enumerate(ordered_members, start=1):
            assignment = assignment_by_post[member.post_uid]
            anchor_score = float(assignment["anchor_score"])
            nearest_score = float(assignment["nearest_score"])
            if not assignment["is_origin"]:
                anchor_scores.append(anchor_score)
                nearest_scores.append(nearest_score)

            perf = perf_lookup.get(member.post_uid, {})
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
                    "family_schema_version": FAMILY_SCHEMA_VERSION,
                    "family_id": family_id,
                    "operator_id": member.operator_id,
                    "post_uid": member.post_uid,
                    "account_id": member.account_id,
                    "account": member.account,
                    "post_id": member.post_id,
                    "created_at": member.created_at,
                    "content_type": member.content_type,
                    "family_member_index": index,
                    "is_family_origin": bool(assignment["is_origin"]),
                    "family_origin_post_uid": family.anchor.post_uid,
                    "days_since_family_origin": _days_between(
                        family.anchor.created_at,
                        member.created_at,
                    ),
                    "match_score_to_origin": anchor_score,
                    "match_score_to_nearest_member": nearest_score,
                    "nearest_member_post_uid": assignment["nearest_post_uid"],
                    "match_reason_json": assignment["match_reason_json"],
                    "topic": member.topic,
                    "content_angle": member.content_angle,
                    "hook_text": member.hook_text,
                    "hook_replicable_formula": member.hook_formula,
                    "creative_formula": member.creative_formula,
                    "sequence_roles_json": json.dumps(
                        list(member.sequence_roles),
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
        representative_post_uid = _representative_post_uid(family, perf_lookup)

        family_rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "family_schema_version": FAMILY_SCHEMA_VERSION,
                "family_id": family_id,
                "operator_id": family.anchor.operator_id,
                "family_origin_post_uid": family.anchor.post_uid,
                "origin_account_id": family.anchor.account_id,
                "origin_account": family.anchor.account,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "lifespan_days": (
                    _days_between(ordered_members[0].created_at, ordered_members[-1].created_at)
                ),
                "member_count": len(ordered_members),
                "variant_count": max(0, len(ordered_members) - 1),
                "accounts_count": len(account_ids),
                "cross_account": len(account_ids) > 1,
                "accounts_json": json.dumps(accounts, ensure_ascii=False),
                "content_types_json": json.dumps(content_types, ensure_ascii=False),
                "representative_post_uid": representative_post_uid,
                "anchor_cohesion_mean": mean_anchor,
                "anchor_cohesion_min": min_anchor,
                "nearest_match_mean": mean_nearest,
                "family_confidence": _confidence(len(ordered_members), mean_anchor),
                "core_topic": family.anchor.topic,
                "core_angle": family.anchor.content_angle,
                "core_hook_text": family.anchor.hook_text,
                "core_hook_formula": family.anchor.hook_formula,
                "core_creative_formula": family.anchor.creative_formula,
                "core_sequence_roles_json": json.dumps(
                    list(family.anchor.sequence_roles),
                    ensure_ascii=False,
                ),
                "median_views_percentile_account": (
                    float(pd.Series(account_percentiles).median())
                    if account_percentiles
                    else None
                ),
                "max_views_percentile_account": (
                    max(account_percentiles) if account_percentiles else None
                ),
                "median_views_percentile_operator": (
                    float(pd.Series(operator_percentiles).median())
                    if operator_percentiles
                    else None
                ),
                "max_views_percentile_operator": (
                    max(operator_percentiles) if operator_percentiles else None
                ),
                "clustering_threshold": threshold,
                "bridge_floor": bridge_floor,
                "clustering_method": "deterministic-greedy-anchor-bridge-v1",
            }
        )

    return {
        "creative_families": pd.DataFrame(family_rows),
        "creative_family_members": pd.DataFrame(member_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic creative-family candidates from canonical posts, "
            "Vision analysis, and sequence evidence. No LLM call is performed."
        )
    )
    parser.add_argument(
        "--posts",
        default="data/05_master/posts.parquet",
    )
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--sequence",
        default="data/05_master/creative_sequence.parquet",
    )
    parser.add_argument(
        "--performance",
        default="data/06_analytics/post_performance.parquet",
        help="Optional performance analytics used only for family summaries/representative choice.",
    )
    parser.add_argument("--out", default="data/06_analytics")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--bridge-floor", type=float, default=DEFAULT_BRIDGE_FLOOR)
    args = parser.parse_args()

    posts_path = Path(args.posts).expanduser().resolve()
    analysis_path = Path(args.analysis).expanduser().resolve()
    sequence_path = Path(args.sequence).expanduser().resolve()
    performance_path = Path(args.performance).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    posts = read_table(posts_path)
    analysis = read_table(analysis_path)
    sequence = read_table(sequence_path)
    performance = read_table(performance_path) if performance_path.exists() else None

    tables = build_creative_family_tables(
        posts,
        analysis,
        sequence,
        performance,
        threshold=args.threshold,
        bridge_floor=args.bridge_floor,
    )

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        table.to_parquet(path, index=False)
        outputs[name] = str(path)

    families = tables["creative_families"]
    members = tables["creative_family_members"]
    multi_post_families = (
        int(families["member_count"].gt(1).sum())
        if "member_count" in families.columns
        else 0
    )
    cross_account_families = (
        int(families["cross_account"].fillna(False).astype(bool).sum())
        if "cross_account" in families.columns
        else 0
    )

    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "family_schema_version": FAMILY_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "posts_source": str(posts_path),
        "analysis_source": str(analysis_path),
        "sequence_source": str(sequence_path),
        "performance_source": str(performance_path) if performance is not None else None,
        "posts": int(len(posts)),
        "families": int(len(families)),
        "multi_post_families": multi_post_families,
        "cross_account_families": cross_account_families,
        "family_members": int(len(members)),
        "threshold": args.threshold,
        "bridge_floor": args.bridge_floor,
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No LLM/Vision call was performed.",
            "Families are deterministic candidates, not causal or strategic claims.",
            "Every assignment retains similarity evidence and stable post_uid lineage.",
        ],
    }
    (out_dir / "creative_families_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
