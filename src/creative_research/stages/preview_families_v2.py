#!/usr/bin/env python3
"""Preview a conservative creative-family v2 model from calibration pair evidence.

This stage never overwrites production creative_families. It consumes the retained
calibration pair table and applies language-aware seed/bridge gates, then performs
chronological greedy clustering with an anchor constraint.

The purpose is to inspect family-size distribution and likely over/under-merging before
changing the production family layer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.stages.build_families import _text_similarity
from creative_research.validation import read_table

PREVIEW_SCHEMA_VERSION = "creative-family-v2-preview-v2"

DEFAULT_STRONG_COMBINED = 0.80
DEFAULT_BRIDGE_COMBINED = 0.75
DEFAULT_MIN_AI_CONFIDENCE = 0.80

AI_POSITIVE_RELATIONSHIPS = {
    "exact_reuse",
    "translation_adaptation",
    "paraphrase",
    "hook_variant",
    "execution_variant",
}
AI_NEGATIVE_RELATIONSHIPS = {"thematic_only", "unrelated"}

SAME_LANGUAGE_STRONG_SEMANTIC = 0.35
SAME_LANGUAGE_STRONG_HOOK = 0.28
SAME_LANGUAGE_STRONG_TOPIC = 0.70
SAME_LANGUAGE_STRONG_TOPIC_PRODUCTION = 0.60
SAME_LANGUAGE_BRIDGE_SEMANTIC = 0.48
SAME_LANGUAGE_BRIDGE_HOOK = 0.40
CROSS_LANGUAGE_STRONG_STRUCTURE = 0.94
CROSS_LANGUAGE_STRONG_SEMANTIC = 0.28
CROSS_LANGUAGE_BRIDGE_STRUCTURE = 0.92
CROSS_LANGUAGE_BRIDGE_SEMANTIC = 0.40


@dataclass(slots=True)
class PreviewFamily:
    operator_id: str
    anchor_post_uid: str
    members: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.members:
            self.members.append(self.anchor_post_uid)


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


def _bool(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _preview_family_id(operator_id: str, anchor_post_uid: str) -> str:
    raw = f"{operator_id}\0{anchor_post_uid}".encode("utf-8")
    return "F2P-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def classify_pair(
    row: dict[str, Any],
    *,
    strong_combined: float = DEFAULT_STRONG_COMBINED,
    bridge_combined: float = DEFAULT_BRIDGE_COMBINED,
) -> str | None:
    combined = _numeric(row.get("combined_score"))
    structure = _numeric(row.get("structure_score"))
    semantic = _numeric(row.get("semantic_text_score"))
    production = _numeric(row.get("production_family_score"))
    cross_language = _bool(row.get("cross_language"))
    same_current_family = _bool(row.get("same_current_family"))

    if same_current_family:
        return "strong_current_family"
    if combined is None or structure is None:
        return None

    if cross_language:
        if (
            combined >= strong_combined
            and structure >= CROSS_LANGUAGE_STRONG_STRUCTURE
            and semantic is not None
            and semantic >= CROSS_LANGUAGE_STRONG_SEMANTIC
        ):
            return "strong_cross_language"
        if (
            combined >= bridge_combined
            and structure >= CROSS_LANGUAGE_BRIDGE_STRUCTURE
            and semantic is not None
            and semantic >= CROSS_LANGUAGE_BRIDGE_SEMANTIC
        ):
            return "bridge_cross_language"
        return None

    hook_similarity = _text_similarity(
        row.get("left_hook_text"),
        row.get("right_hook_text"),
    )
    topic_similarity = _text_similarity(
        row.get("left_topic"),
        row.get("right_topic"),
    )
    strong_concept_coherence = (
        (
            hook_similarity is not None
            and hook_similarity >= SAME_LANGUAGE_STRONG_HOOK
        )
        or (
            topic_similarity is not None
            and topic_similarity >= SAME_LANGUAGE_STRONG_TOPIC
            and production is not None
            and production >= SAME_LANGUAGE_STRONG_TOPIC_PRODUCTION
        )
    )
    if (
        combined >= strong_combined
        and semantic is not None
        and semantic >= SAME_LANGUAGE_STRONG_SEMANTIC
        and strong_concept_coherence
    ):
        return "strong_same_language"
    if (
        combined >= bridge_combined
        and semantic is not None
        and semantic >= SAME_LANGUAGE_BRIDGE_SEMANTIC
        and hook_similarity is not None
        and hook_similarity >= SAME_LANGUAGE_BRIDGE_HOOK
    ):
        return "bridge_same_language"
    return None


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _ai_judgment_lookup(
    judgments: pd.DataFrame | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if (
        judgments is None
        or judgments.empty
        or not {"left_post_uid", "right_post_uid"}.issubset(judgments.columns)
    ):
        return {}
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in judgments.to_dict(orient="records"):
        left = str(row.get("left_post_uid") or "")
        right = str(row.get("right_post_uid") or "")
        if not left or not right:
            continue
        result[_pair_key(left, right)] = row
    return result


def _ai_override(
    judgment: dict[str, Any] | None,
    *,
    min_confidence: float,
) -> str | None:
    if not judgment:
        return None
    confidence = _numeric(judgment.get("confidence"))
    if confidence is None or confidence < min_confidence:
        return None

    decision = str(judgment.get("decision") or "")
    relationship = str(judgment.get("relationship") or "")

    if (
        decision == "different_core_concept"
        or relationship in AI_NEGATIVE_RELATIONSHIPS
    ):
        return "reject_ai_different"

    if (
        decision == "same_core_concept"
        and relationship in AI_POSITIVE_RELATIONSHIPS
    ):
        return "strong_ai_same"

    return None


def _prepare_pairs(
    pairs: pd.DataFrame,
    *,
    strong_combined: float,
    bridge_combined: float,
    ai_judgments: pd.DataFrame | None = None,
    min_ai_confidence: float = DEFAULT_MIN_AI_CONFIDENCE,
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, int],
]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    strong_neighbors: dict[str, set[str]] = {}
    bridge_neighbors: dict[str, set[str]] = {}
    gate_counts: dict[str, int] = {}
    ai_lookup = _ai_judgment_lookup(ai_judgments)

    required = {"left_post_uid", "right_post_uid", "combined_score"}
    missing = sorted(required - set(pairs.columns))
    if missing:
        raise ValueError(
            "family calibration pairs missing required columns: "
            + ", ".join(missing)
        )

    for raw in pairs.to_dict(orient="records"):
        left = str(raw["left_post_uid"])
        right = str(raw["right_post_uid"])
        ai_gate = _ai_override(
            ai_lookup.get(_pair_key(left, right)),
            min_confidence=min_ai_confidence,
        )
        if ai_gate == "reject_ai_different":
            gate_counts[ai_gate] = gate_counts.get(ai_gate, 0) + 1
            continue

        gate = ai_gate or classify_pair(
            raw,
            strong_combined=strong_combined,
            bridge_combined=bridge_combined,
        )
        if gate is None:
            continue
        row = {**raw, "_gate": gate}
        lookup[_pair_key(left, right)] = row
        gate_counts[gate] = gate_counts.get(gate, 0) + 1
        target = (
            strong_neighbors if gate.startswith("strong_") else bridge_neighbors
        )
        target.setdefault(left, set()).add(right)
        target.setdefault(right, set()).add(left)

    return lookup, strong_neighbors, bridge_neighbors, gate_counts


def _post_metadata(
    posts: pd.DataFrame,
    analysis: pd.DataFrame | None,
) -> dict[str, dict[str, Any]]:
    analysis_lookup: dict[str, dict[str, Any]] = {}
    if (
        analysis is not None
        and not analysis.empty
        and "post_uid" in analysis.columns
    ):
        analysis_lookup = {
            str(row["post_uid"]): row
            for row in analysis.to_dict(orient="records")
        }

    required = {
        "post_uid",
        "operator_id",
        "account_id",
        "account",
        "created_at",
    }
    missing = sorted(required - set(posts.columns))
    if missing:
        raise ValueError(
            "posts table missing required columns: " + ", ".join(missing)
        )

    result: dict[str, dict[str, Any]] = {}
    for post in posts.to_dict(orient="records"):
        post_uid = str(post["post_uid"])
        analysis_row = analysis_lookup.get(post_uid, {})
        result[post_uid] = {
            **post,
            "hook_text": analysis_row.get("hook_text"),
            "topic": analysis_row.get("topic"),
            "content_angle": analysis_row.get("content_angle"),
            "primary_language_code": analysis_row.get("primary_language_code"),
        }
    return result


def _chronological_posts(
    metadata: dict[str, dict[str, Any]],
) -> list[str]:
    def key(post_uid: str) -> tuple[str, int, str]:
        row = metadata[post_uid]
        operator_id = str(row.get("operator_id") or "")
        created = pd.to_datetime(
            row.get("created_at"),
            errors="coerce",
            utc=True,
        )
        created_ns = (
            int(created.value)
            if created is not pd.NaT and not pd.isna(created)
            else 2**63 - 1
        )
        return operator_id, created_ns, post_uid

    return sorted(metadata, key=key)


def build_family_v2_preview(
    posts: pd.DataFrame,
    pairs: pd.DataFrame,
    analysis: pd.DataFrame | None = None,
    ai_judgments: pd.DataFrame | None = None,
    *,
    strong_combined: float = DEFAULT_STRONG_COMBINED,
    bridge_combined: float = DEFAULT_BRIDGE_COMBINED,
    min_ai_confidence: float = DEFAULT_MIN_AI_CONFIDENCE,
) -> dict[str, pd.DataFrame | dict[str, Any]]:
    metadata = _post_metadata(posts, analysis)
    pair_lookup, strong_neighbors, bridge_neighbors, gate_counts = _prepare_pairs(
        pairs,
        strong_combined=strong_combined,
        bridge_combined=bridge_combined,
        ai_judgments=ai_judgments,
        min_ai_confidence=min_ai_confidence,
    )

    families: list[PreviewFamily] = []
    family_by_member: dict[str, PreviewFamily] = {}
    assignment: dict[str, dict[str, Any]] = {}

    for post_uid in _chronological_posts(metadata):
        post = metadata[post_uid]
        operator_id = _clean(post.get("operator_id"))
        if not operator_id:
            family = PreviewFamily(
                operator_id=f"UNMAPPED:{post.get('account_id')}",
                anchor_post_uid=post_uid,
            )
            families.append(family)
            family_by_member[post_uid] = family
            assignment[post_uid] = {
                "is_origin": True,
                "anchor_score": 1.0,
                "nearest_score": 1.0,
                "nearest_post_uid": post_uid,
                "nearest_gate": "origin",
                "anchor_gate": "origin",
            }
            continue

        candidate_families: dict[int, PreviewFamily] = {}
        for neighbor in strong_neighbors.get(post_uid, set()):
            existing = family_by_member.get(neighbor)
            if existing is None or existing.operator_id != operator_id:
                continue
            candidate_families[id(existing)] = existing

        best_family: PreviewFamily | None = None
        best_score = -1.0
        best_anchor_score = 0.0
        best_nearest_score = 0.0
        best_nearest_post_uid: str | None = None
        best_anchor_gate: str | None = None
        best_nearest_gate: str | None = None

        for family in candidate_families.values():
            anchor_pair = pair_lookup.get(
                _pair_key(post_uid, family.anchor_post_uid)
            )
            if anchor_pair is None:
                continue

            anchor_gate = str(anchor_pair["_gate"])
            if not (
                anchor_gate.startswith("strong_")
                or anchor_gate.startswith("bridge_")
            ):
                continue

            anchor_score = _numeric(anchor_pair.get("combined_score")) or 0.0

            nearest_score = -1.0
            nearest_uid: str | None = None
            nearest_gate: str | None = None
            for member_uid in family.members:
                member_pair = pair_lookup.get(_pair_key(post_uid, member_uid))
                if member_pair is None:
                    continue
                gate = str(member_pair["_gate"])
                if not gate.startswith("strong_"):
                    continue
                score = _numeric(member_pair.get("combined_score")) or 0.0
                if score > nearest_score:
                    nearest_score = score
                    nearest_uid = member_uid
                    nearest_gate = gate

            if nearest_uid is None:
                continue

            score = 0.35 * anchor_score + 0.65 * nearest_score
            if score > best_score:
                best_family = family
                best_score = score
                best_anchor_score = anchor_score
                best_nearest_score = nearest_score
                best_nearest_post_uid = nearest_uid
                best_anchor_gate = anchor_gate
                best_nearest_gate = nearest_gate

        if best_family is None:
            family = PreviewFamily(
                operator_id=operator_id,
                anchor_post_uid=post_uid,
            )
            families.append(family)
            family_by_member[post_uid] = family
            assignment[post_uid] = {
                "is_origin": True,
                "anchor_score": 1.0,
                "nearest_score": 1.0,
                "nearest_post_uid": post_uid,
                "nearest_gate": "origin",
                "anchor_gate": "origin",
            }
            continue

        best_family.members.append(post_uid)
        family_by_member[post_uid] = best_family
        assignment[post_uid] = {
            "is_origin": False,
            "anchor_score": best_anchor_score,
            "nearest_score": best_nearest_score,
            "nearest_post_uid": best_nearest_post_uid,
            "nearest_gate": best_nearest_gate,
            "anchor_gate": best_anchor_gate,
        }

    member_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []

    for family in families:
        family_id = _preview_family_id(
            family.operator_id,
            family.anchor_post_uid,
        )
        account_ids: set[str] = set()
        accounts: set[str] = set()
        languages: set[str] = set()
        member_scores: list[float] = []

        for index, post_uid in enumerate(family.members, start=1):
            row = metadata[post_uid]
            info = assignment[post_uid]
            account_id = str(row.get("account_id") or "")
            account = str(row.get("account") or "")
            language = _clean(row.get("primary_language_code"))
            account_ids.add(account_id)
            accounts.add(account)
            if language:
                languages.add(language)
            if not info["is_origin"]:
                member_scores.append(float(info["anchor_score"]))

            member_rows.append(
                {
                    "preview_schema_version": PREVIEW_SCHEMA_VERSION,
                    "family_id": family_id,
                    "operator_id": _clean(row.get("operator_id")),
                    "post_uid": post_uid,
                    "account_id": account_id,
                    "account": account,
                    "created_at": row.get("created_at"),
                    "family_member_index": index,
                    "is_family_origin": bool(info["is_origin"]),
                    "family_origin_post_uid": family.anchor_post_uid,
                    "match_score_to_origin": info["anchor_score"],
                    "match_score_to_nearest_member": info["nearest_score"],
                    "nearest_member_post_uid": info["nearest_post_uid"],
                    "anchor_gate": info["anchor_gate"],
                    "nearest_gate": info["nearest_gate"],
                    "hook_text": row.get("hook_text"),
                    "topic": row.get("topic"),
                    "content_angle": row.get("content_angle"),
                    "primary_language_code": language,
                }
            )

        anchor = metadata[family.anchor_post_uid]
        family_rows.append(
            {
                "preview_schema_version": PREVIEW_SCHEMA_VERSION,
                "family_id": family_id,
                "operator_id": _clean(anchor.get("operator_id")),
                "family_origin_post_uid": family.anchor_post_uid,
                "origin_account": anchor.get("account"),
                "origin_hook_text": anchor.get("hook_text"),
                "origin_topic": anchor.get("topic"),
                "origin_angle": anchor.get("content_angle"),
                "member_count": len(family.members),
                "variant_count": max(0, len(family.members) - 1),
                "accounts_count": len(account_ids),
                "cross_account": len(account_ids) > 1,
                "languages_count": len(languages),
                "cross_language": len(languages) > 1,
                "accounts_json": json.dumps(sorted(accounts), ensure_ascii=False),
                "languages_json": json.dumps(sorted(languages), ensure_ascii=False),
                "anchor_score_mean": (
                    float(sum(member_scores) / len(member_scores))
                    if member_scores
                    else None
                ),
                "anchor_score_min": (
                    min(member_scores) if member_scores else None
                ),
            }
        )

    families_df = pd.DataFrame(family_rows)
    members_df = pd.DataFrame(member_rows)

    size_distribution = (
        {
            str(int(key)): int(value)
            for key, value in families_df["member_count"]
            .value_counts()
            .sort_index()
            .items()
        }
        if not families_df.empty
        else {}
    )
    multi = (
        families_df.loc[families_df["member_count"].gt(1)]
        if not families_df.empty
        else families_df
    )
    report = {
        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
        "posts": int(len(posts)),
        "families": int(len(families_df)),
        "multi_post_families": int(len(multi)),
        "posts_in_multi_post_families": (
            int(multi["member_count"].sum()) if not multi.empty else 0
        ),
        "cross_account_families": (
            int(multi["cross_account"].fillna(False).astype(bool).sum())
            if not multi.empty
            else 0
        ),
        "cross_language_families": (
            int(multi["cross_language"].fillna(False).astype(bool).sum())
            if not multi.empty
            else 0
        ),
        "largest_family_size": (
            int(families_df["member_count"].max())
            if not families_df.empty
            else 0
        ),
        "size_distribution": size_distribution,
        "strong_combined": strong_combined,
        "bridge_combined": bridge_combined,
        "min_ai_confidence": min_ai_confidence,
        "ai_judgments_loaded": (
            int(len(ai_judgments))
            if ai_judgments is not None
            else 0
        ),
        "same_language_strong_semantic": SAME_LANGUAGE_STRONG_SEMANTIC,
        "same_language_strong_hook": SAME_LANGUAGE_STRONG_HOOK,
        "same_language_strong_topic": SAME_LANGUAGE_STRONG_TOPIC,
        "same_language_strong_topic_production": SAME_LANGUAGE_STRONG_TOPIC_PRODUCTION,
        "same_language_bridge_semantic": SAME_LANGUAGE_BRIDGE_SEMANTIC,
        "same_language_bridge_hook": SAME_LANGUAGE_BRIDGE_HOOK,
        "cross_language_strong_structure": CROSS_LANGUAGE_STRONG_STRUCTURE,
        "cross_language_strong_semantic": CROSS_LANGUAGE_STRONG_SEMANTIC,
        "cross_language_bridge_structure": CROSS_LANGUAGE_BRIDGE_STRUCTURE,
        "cross_language_bridge_semantic": CROSS_LANGUAGE_BRIDGE_SEMANTIC,
        "gate_counts": gate_counts,
        "notes": [
            "Preview only: production creative_families are not modified.",
            "New families are seeded only by strong pair edges.",
            "Bridge edges can satisfy the anchor constraint but cannot seed a family on their own.",
            "Cross-language gates compensate for lexical penalty but require very high structural similarity.",
            "Same-language gates additionally require hook coherence or strong topic plus production-score coherence.",
            "Same-current-family calibration pairs are retained as strong positive controls unless a high-confidence AI rejection overrides them.",
            "High-confidence AI same-core judgments become strong edges; high-confidence different-core judgments reject an edge; uncertain/low-confidence judgments fall back to deterministic gates.",
        ],
    }

    return {
        "families": families_df,
        "members": members_df,
        "report": report,
    }


def _review_table(
    families: pd.DataFrame,
    members: pd.DataFrame,
    *,
    limit: int = 150,
) -> pd.DataFrame:
    if families.empty or members.empty:
        return pd.DataFrame()
    multi = families.loc[families["member_count"].gt(1)].sort_values(
        ["member_count", "accounts_count", "languages_count", "family_id"],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).head(limit)
    rows: list[dict[str, Any]] = []
    for family in multi.to_dict(orient="records"):
        family_id = str(family["family_id"])
        group = members.loc[members["family_id"].astype(str).eq(family_id)]
        rows.append(
            {
                **family,
                "member_post_uids": " | ".join(group["post_uid"].astype(str)),
                "member_accounts": " | ".join(group["account"].astype(str)),
                "member_languages": " | ".join(
                    group["primary_language_code"].fillna("").astype(str)
                ),
                "member_hooks": " || ".join(
                    group["hook_text"].fillna("").astype(str)
                ),
                "member_topics": " || ".join(
                    group["topic"].fillna("").astype(str)
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview a conservative creative-family v2 clustering model from "
            "family calibration pair evidence without overwriting production families."
        )
    )
    parser.add_argument("--posts", default="data/05_master/posts.parquet")
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--pairs",
        default=(
            "data/06_analytics/family_calibration/"
            "family_calibration_pairs.parquet"
        ),
    )
    parser.add_argument(
        "--out",
        default="data/06_analytics/family_v2_preview",
    )
    parser.add_argument(
        "--ai-judgments",
        default="data/06_analytics/family_ai/family_ai_judgments.parquet",
        help="Optional AI pair judgments; missing file falls back to deterministic gates.",
    )
    parser.add_argument(
        "--min-ai-confidence",
        type=float,
        default=DEFAULT_MIN_AI_CONFIDENCE,
    )
    parser.add_argument(
        "--strong-combined",
        type=float,
        default=DEFAULT_STRONG_COMBINED,
    )
    parser.add_argument(
        "--bridge-combined",
        type=float,
        default=DEFAULT_BRIDGE_COMBINED,
    )
    parser.add_argument("--review-limit", type=int, default=150)
    args = parser.parse_args()

    posts_path = Path(args.posts).expanduser().resolve()
    analysis_path = Path(args.analysis).expanduser().resolve()
    pairs_path = Path(args.pairs).expanduser().resolve()
    ai_judgments_path = Path(args.ai_judgments).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    posts = read_table(posts_path)
    analysis = read_table(analysis_path)
    pairs = read_table(pairs_path)
    ai_judgments = (
        read_table(ai_judgments_path)
        if ai_judgments_path.exists()
        else None
    )

    result = build_family_v2_preview(
        posts,
        pairs,
        analysis,
        ai_judgments,
        strong_combined=args.strong_combined,
        bridge_combined=args.bridge_combined,
        min_ai_confidence=args.min_ai_confidence,
    )
    families = result["families"]
    members = result["members"]
    report = dict(result["report"])

    families_path = out_dir / "family_v2_preview_families.parquet"
    members_path = out_dir / "family_v2_preview_members.parquet"
    review_path = out_dir / "family_v2_preview_review.csv"
    report_path = out_dir / "family_v2_preview_report.json"

    assert isinstance(families, pd.DataFrame)
    assert isinstance(members, pd.DataFrame)
    families.to_parquet(families_path, index=False)
    members.to_parquet(members_path, index=False)
    _review_table(
        families,
        members,
        limit=max(1, args.review_limit),
    ).to_csv(review_path, index=False, encoding="utf-8-sig")

    report.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "posts_source": str(posts_path),
            "analysis_source": str(analysis_path),
            "pairs_source": str(pairs_path),
            "ai_judgments_source": (
                str(ai_judgments_path)
                if ai_judgments is not None
                else None
            ),
            "outputs": {
                "families": str(families_path),
                "members": str(members_path),
                "review_csv": str(review_path),
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
