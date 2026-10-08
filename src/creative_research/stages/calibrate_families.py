#!/usr/bin/env python3
"""Measure creative-family similarity behavior on real data without changing families.

This diagnostic stage exists to calibrate family discovery before changing production
clustering thresholds. It compares posts inside each verified operator using two separate
views:

1. structure_score: language-independent taxonomy + sequence similarity;
2. semantic_text_score: Vision-generated descriptive text similarity, when available.

The existing production family score is also recorded for comparison. No family assignment
is mutated and no LLM/Vision call is performed.
"""
from __future__ import annotations

import argparse
import heapq
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.stages.build_families import (
    _build_features,
    _clean,
    _exact_similarity,
    _normalize_text,
    _sequence_similarity,
    _text_similarity,
    compare_features,
)
from creative_research.validation import read_table

CALIBRATION_SCHEMA_VERSION = "creative-family-calibration-v1"

STRUCTURE_WEIGHTS: dict[str, float] = {
    "content_angle": 0.20,
    "value_type": 0.12,
    "audience_segment": 0.08,
    "hook_technique": 0.08,
    "format": 0.08,
    "product_family": 0.05,
    "product_placement_style": 0.05,
    "cta_type": 0.04,
    "dominant_visual_type": 0.05,
    "sequence_roles": 0.15,
    "sequence_visual_types": 0.10,
}

SEMANTIC_TEXT_WEIGHTS: dict[str, float] = {
    "niche": 0.10,
    "topic": 0.20,
    "pain_point": 0.15,
    "desired_outcome": 0.15,
    "hook_formula": 0.10,
    "creative_formula": 0.15,
    "visual_description": 0.15,
}

DEFAULT_MIN_STRUCTURE = 0.42
DEFAULT_MIN_COMBINED = 0.55
DEFAULT_MAX_PAIRS = 50_000

SCORE_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)


@dataclass(frozen=True, slots=True)
class CalibrationPost:
    post_uid: str
    operator_id: str
    account_id: str
    account: str
    created_at: Any
    content_type: str | None
    primary_language_code: str | None
    audience_segment: str | None
    niche: str | None
    topic: str | None
    content_angle: str | None
    value_type: str | None
    pain_point: str | None
    desired_outcome: str | None
    hook_text: str | None
    hook_technique: str | None
    hook_formula: str | None
    creative_formula: str | None
    format_value: str | None
    product_family: str | None
    product_placement_style: str | None
    cta_type: str | None
    dominant_visual_type: str | None
    sequence_roles: tuple[str, ...]
    sequence_visual_types: tuple[str, ...]
    visual_description: str


def _format_value(row: dict[str, Any]) -> str | None:
    return _clean(row.get("content_format")) or _clean(row.get("video_format"))


def _sequence_features(
    sequence: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    if sequence.empty or "post_uid" not in sequence.columns:
        return {}
    work = sequence.copy()
    if "position" in work.columns:
        work["_position"] = pd.to_numeric(work["position"], errors="coerce")
        work = work.sort_values(
            ["post_uid", "_position"],
            kind="mergesort",
            na_position="last",
        )
    result: dict[str, dict[str, Any]] = {}
    for post_uid, group in work.groupby("post_uid", sort=False, dropna=True):
        roles = tuple(
            value
            for value in (
                _normalize_text(item)
                for item in group.get("role", pd.Series(dtype="object"))
            )
            if value
        )
        visual_types = tuple(
            value
            for value in (
                _normalize_text(item)
                for item in group.get("visual_type", pd.Series(dtype="object"))
            )
            if value
        )
        descriptions = [
            _clean(item)
            for item in group.get("visual_description", pd.Series(dtype="object"))
        ]
        result[str(post_uid)] = {
            "roles": roles,
            "visual_types": visual_types,
            "visual_description": " ".join(
                value for value in descriptions if value
            ),
        }
    return result


def _build_calibration_posts(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
) -> list[CalibrationPost]:
    required = {
        "post_uid",
        "operator_id",
        "account_id",
        "account",
        "created_at",
        "content_type",
    }
    missing = sorted(required - set(posts.columns))
    if missing:
        raise ValueError(f"posts table missing required columns: {', '.join(missing)}")
    if "post_uid" not in analysis.columns:
        raise ValueError("creative_analysis missing post_uid")

    analysis_lookup = {
        str(row["post_uid"]): row
        for row in analysis.to_dict(orient="records")
    }
    sequence_lookup = _sequence_features(sequence)
    rows: list[CalibrationPost] = []

    for post in posts.to_dict(orient="records"):
        operator_id = _clean(post.get("operator_id"))
        if not operator_id:
            continue
        post_uid = str(post["post_uid"])
        a = analysis_lookup.get(post_uid, {})
        seq = sequence_lookup.get(post_uid, {})
        rows.append(
            CalibrationPost(
                post_uid=post_uid,
                operator_id=operator_id,
                account_id=str(post.get("account_id") or ""),
                account=str(post.get("account") or ""),
                created_at=post.get("created_at"),
                content_type=_clean(post.get("content_type")),
                primary_language_code=_clean(a.get("primary_language_code")),
                audience_segment=_clean(a.get("audience_segment")),
                niche=_clean(a.get("niche")),
                topic=_clean(a.get("topic")),
                content_angle=_clean(a.get("content_angle")),
                value_type=_clean(a.get("value_type")),
                pain_point=_clean(a.get("pain_point")),
                desired_outcome=_clean(a.get("desired_outcome")),
                hook_text=_clean(a.get("hook_text")),
                hook_technique=_clean(a.get("hook_technique")),
                hook_formula=_clean(a.get("hook_replicable_formula")),
                creative_formula=_clean(a.get("creative_formula")),
                format_value=_format_value(a),
                product_family=_clean(a.get("product_family")),
                product_placement_style=_clean(a.get("product_placement_style")),
                cta_type=_clean(a.get("cta_type")),
                dominant_visual_type=_clean(a.get("dominant_visual_type")),
                sequence_roles=tuple(seq.get("roles", ())),
                sequence_visual_types=tuple(seq.get("visual_types", ())),
                visual_description=str(seq.get("visual_description") or ""),
            )
        )

    rows.sort(
        key=lambda item: (
            item.operator_id,
            str(item.created_at or ""),
            item.post_uid,
        )
    )
    return rows


def _weighted_score(
    components: dict[str, float | None],
    weights: dict[str, float],
) -> float | None:
    available = [
        (float(value), weights[name])
        for name, value in components.items()
        if value is not None
    ]
    if not available:
        return None
    denominator = sum(weight for _, weight in available)
    if denominator <= 0:
        return None
    return float(
        sum(value * weight for value, weight in available)
        / denominator
    )


def structure_components(
    left: CalibrationPost,
    right: CalibrationPost,
) -> dict[str, float | None]:
    return {
        "content_angle": _exact_similarity(
            left.content_angle,
            right.content_angle,
        ),
        "value_type": _exact_similarity(left.value_type, right.value_type),
        "audience_segment": _exact_similarity(
            left.audience_segment,
            right.audience_segment,
        ),
        "hook_technique": _exact_similarity(
            left.hook_technique,
            right.hook_technique,
        ),
        "format": _exact_similarity(left.format_value, right.format_value),
        "product_family": _exact_similarity(
            left.product_family,
            right.product_family,
        ),
        "product_placement_style": _exact_similarity(
            left.product_placement_style,
            right.product_placement_style,
        ),
        "cta_type": _exact_similarity(left.cta_type, right.cta_type),
        "dominant_visual_type": _exact_similarity(
            left.dominant_visual_type,
            right.dominant_visual_type,
        ),
        "sequence_roles": _sequence_similarity(
            left.sequence_roles,
            right.sequence_roles,
        ),
        "sequence_visual_types": _sequence_similarity(
            left.sequence_visual_types,
            right.sequence_visual_types,
        ),
    }


def semantic_text_components(
    left: CalibrationPost,
    right: CalibrationPost,
) -> dict[str, float | None]:
    return {
        "niche": _text_similarity(left.niche, right.niche),
        "topic": _text_similarity(left.topic, right.topic),
        "pain_point": _text_similarity(left.pain_point, right.pain_point),
        "desired_outcome": _text_similarity(
            left.desired_outcome,
            right.desired_outcome,
        ),
        "hook_formula": _text_similarity(
            left.hook_formula,
            right.hook_formula,
        ),
        "creative_formula": _text_similarity(
            left.creative_formula,
            right.creative_formula,
        ),
        "visual_description": _text_similarity(
            left.visual_description,
            right.visual_description,
        ),
    }


def _family_lookup(
    members: pd.DataFrame | None,
) -> dict[str, str]:
    if (
        members is None
        or members.empty
        or not {"post_uid", "family_id"}.issubset(members.columns)
    ):
        return {}
    return {
        str(row["post_uid"]): str(row["family_id"])
        for row in members.to_dict(orient="records")
        if row.get("post_uid") is not None and row.get("family_id") is not None
    }


def _production_feature_lookup(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
) -> dict[str, Any]:
    features = _build_features(posts, analysis, sequence)
    return {feature.post_uid: feature for feature in features}


def _pair_row(
    left: CalibrationPost,
    right: CalibrationPost,
    *,
    structure: float,
    semantic_text: float | None,
    production_score: float | None,
    current_family_lookup: dict[str, str],
    structure_parts: dict[str, float | None],
    semantic_parts: dict[str, float | None],
) -> dict[str, Any]:
    combined = (
        0.72 * structure + 0.28 * semantic_text
        if semantic_text is not None
        else structure
    )
    left_family = current_family_lookup.get(left.post_uid)
    right_family = current_family_lookup.get(right.post_uid)
    return {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "operator_id": left.operator_id,
        "left_post_uid": left.post_uid,
        "right_post_uid": right.post_uid,
        "left_account": left.account,
        "right_account": right.account,
        "cross_account": left.account_id != right.account_id,
        "left_language": left.primary_language_code,
        "right_language": right.primary_language_code,
        "cross_language": (
            bool(left.primary_language_code)
            and bool(right.primary_language_code)
            and left.primary_language_code != right.primary_language_code
        ),
        "left_content_type": left.content_type,
        "right_content_type": right.content_type,
        "left_angle": left.content_angle,
        "right_angle": right.content_angle,
        "left_value_type": left.value_type,
        "right_value_type": right.value_type,
        "left_hook_technique": left.hook_technique,
        "right_hook_technique": right.hook_technique,
        "left_format": left.format_value,
        "right_format": right.format_value,
        "left_topic": left.topic,
        "right_topic": right.topic,
        "left_hook_text": left.hook_text,
        "right_hook_text": right.hook_text,
        "structure_score": structure,
        "semantic_text_score": semantic_text,
        "combined_score": combined,
        "production_family_score": production_score,
        "same_current_family": (
            left_family is not None
            and right_family is not None
            and left_family == right_family
        ),
        "left_current_family_id": left_family,
        "right_current_family_id": right_family,
        "structure_components_json": json.dumps(
            structure_parts,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "semantic_text_components_json": json.dumps(
            semantic_parts,
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def calibrate_family_pairs(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame,
    members: pd.DataFrame | None = None,
    *,
    min_structure: float = DEFAULT_MIN_STRUCTURE,
    min_combined: float = DEFAULT_MIN_COMBINED,
    max_pairs: int = DEFAULT_MAX_PAIRS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    calibration_posts = _build_calibration_posts(posts, analysis, sequence)
    production_lookup = _production_feature_lookup(posts, analysis, sequence)
    family_lookup = _family_lookup(members)

    by_operator: dict[str, list[CalibrationPost]] = {}
    for item in calibration_posts:
        by_operator.setdefault(item.operator_id, []).append(item)

    pair_heap: list[tuple[float, int, dict[str, Any]]] = []
    pair_counter = 0
    all_pairs = 0
    structure_screened = 0
    semantic_scored = 0
    retained_before_cap = 0
    cross_language_retained = 0
    same_family_retained = 0

    threshold_counts = {
        f"{threshold:.2f}": {
            "combined": 0,
            "cross_language": 0,
            "cross_account": 0,
            "currently_split": 0,
        }
        for threshold in SCORE_THRESHOLDS
    }
    structure_threshold_counts = {
        f"{threshold:.2f}": 0
        for threshold in SCORE_THRESHOLDS
    }

    for operator_id in sorted(by_operator):
        operator_posts = by_operator[operator_id]
        for index, left in enumerate(operator_posts):
            for right in operator_posts[index + 1 :]:
                all_pairs += 1
                structure_parts = structure_components(left, right)
                structure = _weighted_score(
                    structure_parts,
                    STRUCTURE_WEIGHTS,
                )
                if structure is None:
                    continue
                for threshold in SCORE_THRESHOLDS:
                    if structure >= threshold:
                        structure_threshold_counts[f"{threshold:.2f}"] += 1

                if structure < min_structure:
                    continue
                structure_screened += 1

                semantic_parts = semantic_text_components(left, right)
                semantic_text = _weighted_score(
                    semantic_parts,
                    SEMANTIC_TEXT_WEIGHTS,
                )
                semantic_scored += 1

                production_score: float | None = None
                left_prod = production_lookup.get(left.post_uid)
                right_prod = production_lookup.get(right.post_uid)
                if left_prod is not None and right_prod is not None:
                    production_score = compare_features(
                        left_prod,
                        right_prod,
                    )[0]

                row = _pair_row(
                    left,
                    right,
                    structure=structure,
                    semantic_text=semantic_text,
                    production_score=production_score,
                    current_family_lookup=family_lookup,
                    structure_parts=structure_parts,
                    semantic_parts=semantic_parts,
                )
                combined = float(row["combined_score"])

                for threshold in SCORE_THRESHOLDS:
                    if combined >= threshold:
                        bucket = threshold_counts[f"{threshold:.2f}"]
                        bucket["combined"] += 1
                        bucket["cross_language"] += int(row["cross_language"])
                        bucket["cross_account"] += int(row["cross_account"])
                        bucket["currently_split"] += int(
                            not row["same_current_family"]
                        )

                if combined < min_combined:
                    continue

                retained_before_cap += 1
                cross_language_retained += int(row["cross_language"])
                same_family_retained += int(row["same_current_family"])
                pair_counter += 1
                heap_item = (combined, pair_counter, row)
                if max_pairs <= 0:
                    continue
                if len(pair_heap) < max_pairs:
                    heapq.heappush(pair_heap, heap_item)
                elif combined > pair_heap[0][0]:
                    heapq.heapreplace(pair_heap, heap_item)

    retained = [
        item[2]
        for item in sorted(
            pair_heap,
            key=lambda item: (-item[0], item[1]),
        )
    ]
    pairs = pd.DataFrame(retained)

    if not pairs.empty:
        pairs = pairs.sort_values(
            [
                "combined_score",
                "structure_score",
                "semantic_text_score",
                "left_post_uid",
                "right_post_uid",
            ],
            ascending=[False, False, False, True, True],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)

    score_quantiles: dict[str, float | None] = {}
    if not pairs.empty:
        for column in (
            "structure_score",
            "semantic_text_score",
            "combined_score",
            "production_family_score",
        ):
            values = pd.to_numeric(pairs[column], errors="coerce").dropna()
            for q in (0.50, 0.75, 0.90, 0.95, 0.99):
                score_quantiles[f"{column}_p{int(q * 100)}"] = (
                    float(values.quantile(q)) if not values.empty else None
                )

    report = {
        "calibration_schema_version": CALIBRATION_SCHEMA_VERSION,
        "posts": len(calibration_posts),
        "operators": len(by_operator),
        "all_operator_pairs": all_pairs,
        "structure_screened_pairs": structure_screened,
        "semantic_scored_pairs": semantic_scored,
        "retained_pairs_before_cap": retained_before_cap,
        "retained_pairs_written": len(pairs),
        "max_pairs": max_pairs,
        "min_structure": min_structure,
        "min_combined": min_combined,
        "retained_cross_language_pairs": cross_language_retained,
        "retained_same_current_family_pairs": same_family_retained,
        "retained_currently_split_pairs": (
            retained_before_cap - same_family_retained
        ),
        "structure_threshold_counts": structure_threshold_counts,
        "combined_threshold_counts": threshold_counts,
        "score_quantiles_on_written_pairs": score_quantiles,
        "notes": [
            "Calibration does not mutate production family assignments.",
            "Structure score is language-independent and uses fixed Vision taxonomy plus ordered sequence roles/visual types.",
            "Semantic text score uses existing Vision descriptive text and may still be language-sensitive.",
            "Production family score is recorded only for comparison with the current clustering model.",
            "Threshold counts are diagnostic evidence, not automatically selected production thresholds.",
        ],
    }
    return pairs, report


def _review_sample(pairs: pd.DataFrame, per_bucket: int = 30) -> pd.DataFrame:
    if pairs.empty:
        return pairs.copy()
    work = pairs.copy()
    work["score_bucket"] = pd.cut(
        work["combined_score"],
        bins=[0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 1.000001],
        labels=[
            "55-60",
            "60-65",
            "65-70",
            "70-75",
            "75-80",
            "80-85",
            "85+",
        ],
        include_lowest=True,
        right=False,
    )
    rows: list[pd.DataFrame] = []
    for _, group in work.groupby(
        ["score_bucket", "cross_language"],
        observed=True,
        sort=True,
    ):
        rows.append(
            group.sort_values(
                ["combined_score", "structure_score"],
                ascending=False,
                kind="mergesort",
            ).head(per_bucket)
        )
    if not rows:
        return work.head(0)
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Measure language-independent structure similarity and Vision-text similarity "
            "to calibrate creative-family discovery without changing production families."
        )
    )
    parser.add_argument("--posts", default="data/05_master/posts.parquet")
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--sequence",
        default="data/05_master/creative_sequence.parquet",
    )
    parser.add_argument(
        "--members",
        default="data/06_analytics/creative_family_members.parquet",
        help="Optional current family membership for split-vs-grouped diagnostics.",
    )
    parser.add_argument(
        "--out",
        default="data/06_analytics/family_calibration",
    )
    parser.add_argument(
        "--min-structure",
        type=float,
        default=DEFAULT_MIN_STRUCTURE,
    )
    parser.add_argument(
        "--min-combined",
        type=float,
        default=DEFAULT_MIN_COMBINED,
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=DEFAULT_MAX_PAIRS,
    )
    parser.add_argument(
        "--review-per-bucket",
        type=int,
        default=30,
    )
    args = parser.parse_args()

    posts_path = Path(args.posts).expanduser().resolve()
    analysis_path = Path(args.analysis).expanduser().resolve()
    sequence_path = Path(args.sequence).expanduser().resolve()
    members_path = Path(args.members).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    posts = read_table(posts_path)
    analysis = read_table(analysis_path)
    sequence = read_table(sequence_path)
    members = read_table(members_path) if members_path.exists() else None

    pairs, report = calibrate_family_pairs(
        posts,
        analysis,
        sequence,
        members,
        min_structure=args.min_structure,
        min_combined=args.min_combined,
        max_pairs=args.max_pairs,
    )
    review = _review_sample(
        pairs,
        per_bucket=max(1, args.review_per_bucket),
    )

    pairs_path = out_dir / "family_calibration_pairs.parquet"
    csv_path = out_dir / "family_calibration_review.csv"
    report_path = out_dir / "family_calibration_report.json"

    pairs.to_parquet(pairs_path, index=False)
    review.to_csv(csv_path, index=False, encoding="utf-8-sig")

    report.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "posts_source": str(posts_path),
            "analysis_source": str(analysis_path),
            "sequence_source": str(sequence_path),
            "members_source": (
                str(members_path) if members is not None else None
            ),
            "outputs": {
                "pairs": str(pairs_path),
                "review_csv": str(csv_path),
                "report": str(report_path),
            },
        }
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
