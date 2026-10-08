#!/usr/bin/env python3
"""Human review workflow for evidence-derived knowledge.

This stage never changes inference logic and never auto-approves knowledge. It:
- rebuilds current knowledge candidates in memory from durable analytics;
- collapses duplicate strategy/lesson representations to one source-level review target;
- writes a prioritized human review queue and editable decisions CSV;
- applies approve/reject/hold decisions to local knowledge_reviews.toml.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.knowledge_reviews import (
    ALLOWED_DECISIONS,
    KnowledgeReview,
    load_knowledge_reviews,
    upsert_knowledge_reviews,
)
from creative_research.pathing import project_root
from creative_research.stages.promote_knowledge import build_knowledge_tables
from creative_research.validation import read_table

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


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


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
            str(key): group
            for key, group in evidence.groupby("knowledge_id", sort=False)
        }

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    unresolved = 0
    for row in catalog.to_dict(orient="records"):
        status = str(row.get("knowledge_status") or "")
        if (
            not include_reviewed
            and status not in {"review_candidate", "promoted"}
        ):
            continue
        source_type, source_id = _review_target(row)
        if source_type is None or source_id is None:
            unresolved += 1
            continue
        grouped.setdefault((source_type, source_id), []).append(row)

    rows: list[dict[str, Any]] = []
    for (source_type, source_id), items in grouped.items():
        knowledge_ids = sorted(
            {str(item["knowledge_id"]) for item in items}
        )
        knowledge_types = {
            str(item.get("knowledge_type") or "") for item in items
        }
        subtypes = {
            str(item.get("subtype") or "") for item in items
        }
        statuses = {
            str(item.get("knowledge_status") or "") for item in items
        }
        scope_types = {
            str(item.get("scope_type") or "") for item in items
        }
        scope_ids = {
            str(item.get("scope_id") or "") for item in items
        }
        confidences = [
            float(value)
            for value in pd.to_numeric(
                pd.Series(
                    [item.get("confidence_score") for item in items]
                ),
                errors="coerce",
            )
            .dropna()
            .tolist()
        ]
        pattern_ids: list[str] = []
        family_ids: list[str] = []
        exceptions: list[str] = []
        for item in items:
            pattern_ids.extend(
                _parse_json_list(item.get("source_pattern_ids_json"))
            )
            family_ids.extend(
                _parse_json_list(item.get("source_family_ids_json"))
            )
            exceptions.extend(
                _parse_json_list(item.get("exceptions_json"))
            )

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
                int(
                    evidence_group["post_uid"]
                    .dropna()
                    .astype(str)
                    .nunique()
                )
                if "post_uid" in evidence_group.columns
                else 0
            )
            linked_family_count = (
                int(
                    evidence_group["family_id"]
                    .dropna()
                    .astype(str)
                    .nunique()
                )
                if "family_id" in evidence_group.columns
                else 0
            )
            linked_pattern_count = (
                int(
                    evidence_group["pattern_id"]
                    .dropna()
                    .astype(str)
                    .nunique()
                )
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
                "existing_review_decision": (
                    representative.get("review_decision")
                ),
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


def _review_packet(queue: pd.DataFrame) -> str:
    lines = [
        "# Knowledge Human Review Queue",
        "",
        (
            "Review decisions are source-level: one hypothesis review can update "
            "both its strategy and lesson knowledge items."
        ),
        "",
        "Decision meanings:",
        "- approve: human-validated for this recorded scope;",
        "- reject: evidence/claim is not trustworthy enough;",
        "- hold: potentially useful, but needs more evidence or inspection.",
        "",
    ]
    if queue.empty:
        lines.append("No pending review sources.")
        return "\n".join(lines) + "\n"

    for row in queue.to_dict(orient="records"):
        lines.extend(
            [
                (
                    f"## {int(row['review_order'])}. "
                    f"Tier {int(row['priority_tier'])} — {row['title']}"
                ),
                "",
                (
                    f"- Target: {row['review_source_type']}:"
                    f"{row['review_source_id']}"
                ),
                f"- Confidence: {row['confidence_max']}",
                f"- Knowledge types: {row['knowledge_types_json']}",
                f"- Subtypes: {row['subtypes_json']}",
                (
                    f"- Evidence links: {int(row['evidence_link_count'])}; "
                    f"posts: {int(row['evidence_post_count'])}; "
                    f"families: {int(row['evidence_family_count'])}; "
                    f"patterns: {int(row['evidence_pattern_count'])}"
                ),
                f"- Review focus: {row['review_focus']}",
                "",
                str(row["statement"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _build_current_knowledge(
    *,
    hypotheses_path: Path,
    strategy_evidence_path: Path,
    families_path: Path,
    family_members_path: Path,
    reviews_path: Path | None,
) -> dict[str, pd.DataFrame]:
    hypotheses = read_table(hypotheses_path)
    strategy_evidence = (
        read_table(strategy_evidence_path)
        if strategy_evidence_path.exists()
        else None
    )
    families = (
        read_table(families_path)
        if families_path.exists()
        else None
    )
    family_members = (
        read_table(family_members_path)
        if family_members_path.exists()
        else None
    )
    reviews = (
        load_knowledge_reviews(reviews_path)
        if reviews_path is not None and reviews_path.exists()
        else {}
    )
    return build_knowledge_tables(
        hypotheses,
        strategy_evidence,
        families,
        family_members,
        reviews=reviews,
    )


def _queue_command(args: argparse.Namespace) -> None:
    root = project_root().resolve()
    hypotheses_path = _resolve(root, args.hypotheses)
    strategy_evidence_path = _resolve(root, args.strategy_evidence)
    families_path = _resolve(root, args.families)
    family_members_path = _resolve(root, args.family_members)
    reviews_path = _resolve(root, args.reviews) if args.reviews else None
    out_dir = _resolve(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = _build_current_knowledge(
        hypotheses_path=hypotheses_path,
        strategy_evidence_path=strategy_evidence_path,
        families_path=families_path,
        family_members_path=family_members_path,
        reviews_path=reviews_path,
    )
    queue, queue_meta = build_review_queue(
        tables["knowledge_catalog"],
        tables["knowledge_evidence_links"],
        include_reviewed=args.include_reviewed,
    )

    queue_csv = out_dir / "knowledge_review_queue.csv"
    queue_jsonl = out_dir / "knowledge_review_queue.jsonl"
    decisions_csv = out_dir / "knowledge_review_decisions.csv"
    packet_md = out_dir / "knowledge_review_packet.md"
    report_json = out_dir / "knowledge_review_report.json"

    queue.to_csv(queue_csv, index=False, encoding="utf-8-sig")
    with queue_jsonl.open("w", encoding="utf-8") as handle:
        for row in queue.to_dict(orient="records"):
            handle.write(
                json.dumps(row, ensure_ascii=False, default=str) + "\n"
            )

    decision_columns = [
        "review_order",
        "priority_tier",
        "review_source_type",
        "review_source_id",
        "title",
        "confidence_max",
        "review_focus",
        "decision",
        "note",
        "reviewed_by",
        "reviewed_at",
    ]
    base_columns = [
        column
        for column in decision_columns
        if column
        not in {"decision", "note", "reviewed_by", "reviewed_at"}
    ]
    if queue.empty:
        decisions = pd.DataFrame(columns=decision_columns)
    else:
        decisions = queue[base_columns].copy()
        for column in (
            "decision",
            "note",
            "reviewed_by",
            "reviewed_at",
        ):
            decisions[column] = ""
        decisions = decisions[decision_columns]
    decisions.to_csv(decisions_csv, index=False, encoding="utf-8-sig")
    packet_md.write_text(_review_packet(queue), encoding="utf-8")

    catalog = tables["knowledge_catalog"]
    tier_counts = (
        {
            str(int(key)): int(value)
            for key, value in queue["priority_tier"]
            .value_counts()
            .sort_index()
            .items()
        }
        if not queue.empty
        else {}
    )
    report = {
        "review_workflow_schema_version": REVIEW_WORKFLOW_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "knowledge_items": int(len(catalog)),
        "review_sources": int(len(queue)),
        "priority_tier_counts": tier_counts,
        **queue_meta,
        "reviews_source": (
            str(reviews_path)
            if reviews_path is not None and reviews_path.exists()
            else None
        ),
        "outputs": {
            "queue_csv": str(queue_csv),
            "queue_jsonl": str(queue_jsonl),
            "decisions_csv": str(decisions_csv),
            "packet_md": str(packet_md),
            "report": str(report_json),
        },
        "notes": [
            "Queue is source-level, not knowledge-item-level.",
            "No review decision is created automatically.",
            (
                "Tier 1 prioritizes operating-model/account-role evidence "
                "and auto-promoted items."
            ),
            (
                "Temporal strategy shifts are intentionally reviewed after "
                "operating-model evidence."
            ),
        ],
    }
    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not queue.empty:
        print("\nTop review targets:")
        for row in queue.head(max(1, args.show)).to_dict(orient="records"):
            print(
                f"  {int(row['review_order']):>2}. "
                f"T{int(row['priority_tier'])} "
                f"{row['review_source_type']}:{row['review_source_id']} "
                f"conf={row['confidence_max']} · {row['title']}"
            )
    print(
        "\nEdit decisions: "
        f"{decisions_csv}\n"
        "Then apply them with: "
        "uv run creative-research review-knowledge apply"
    )


def _review_from_args(
    *,
    source_type: str,
    source_id: str,
    decision: str,
    note: str | None,
    reviewed_by: str | None,
    reviewed_at: str | None,
) -> KnowledgeReview:
    source_type = source_type.strip()
    source_id = source_id.strip()
    decision = decision.strip().lower()
    if not source_type or not source_id:
        raise ValueError("review source type/id are required")
    if source_type not in {"hypothesis", "family", "playbook_sources"}:
        raise ValueError(
            "review_source_type must be hypothesis, family, or playbook_sources"
        )
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(
            "decision must be one of "
            + ", ".join(sorted(ALLOWED_DECISIONS))
        )
    return KnowledgeReview(
        source_type=source_type,
        source_id=source_id,
        decision=decision,
        note=note.strip() if note and note.strip() else None,
        reviewed_by=(
            reviewed_by.strip()
            if reviewed_by and reviewed_by.strip()
            else None
        ),
        reviewed_at=(
            reviewed_at.strip()
            if reviewed_at and reviewed_at.strip()
            else datetime.now(UTC).isoformat()
        ),
    )


def _decide_command(args: argparse.Namespace) -> None:
    root = project_root().resolve()
    reviews_path = _resolve(root, args.reviews)
    review = _review_from_args(
        source_type=args.source_type,
        source_id=args.source_id,
        decision=args.decision,
        note=args.note,
        reviewed_by=args.reviewed_by,
        reviewed_at=args.reviewed_at,
    )
    reviews = upsert_knowledge_reviews(reviews_path, [review])
    print(
        f"Saved {review.decision}: "
        f"{review.source_type}:{review.source_id}\n"
        f"Reviews file: {reviews_path}\n"
        f"Total review decisions: {len(reviews)}"
    )
    print(
        "\nApply to knowledge/workspace with:\n"
        "  uv run creative-research intelligence-build "
        "--from-stage knowledge --force "
        f"--reviews {args.reviews}"
    )


def _apply_command(args: argparse.Namespace) -> None:
    root = project_root().resolve()
    decisions_path = _resolve(root, args.decisions)
    reviews_path = _resolve(root, args.reviews)
    frame = pd.read_csv(decisions_path, dtype=str).fillna("")
    required = {"review_source_type", "review_source_id", "decision"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(
            "decisions CSV missing columns: " + ", ".join(missing)
        )

    incoming: list[KnowledgeReview] = []
    for row in frame.to_dict(orient="records"):
        decision = str(row.get("decision") or "").strip()
        if not decision:
            continue
        incoming.append(
            _review_from_args(
                source_type=str(row.get("review_source_type") or ""),
                source_id=str(row.get("review_source_id") or ""),
                decision=decision,
                note=str(row.get("note") or ""),
                reviewed_by=(
                    str(row.get("reviewed_by") or "")
                    or args.reviewed_by
                ),
                reviewed_at=str(row.get("reviewed_at") or ""),
            )
        )

    if not incoming:
        print("No non-empty decisions found; reviews file was not changed.")
        return

    reviews = upsert_knowledge_reviews(reviews_path, incoming)
    counts = pd.Series(
        [review.decision for review in incoming],
        dtype="object",
    ).value_counts().to_dict()
    print(
        json.dumps(
            {
                "applied": len(incoming),
                "decision_counts": counts,
                "reviews_file": str(reviews_path),
                "total_review_decisions": len(reviews),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        "\nApply to knowledge/workspace with:\n"
        "  uv run creative-research intelligence-build "
        "--from-stage knowledge --force "
        f"--reviews {args.reviews}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build and apply a human review queue for evidence-derived knowledge."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=False)

    queue_parser = subparsers.add_parser(
        "queue",
        help="Generate prioritized source-level review queue.",
    )
    queue_parser.add_argument(
        "--hypotheses",
        default="data/06_analytics/strategy_hypotheses.parquet",
    )
    queue_parser.add_argument(
        "--strategy-evidence",
        default="data/06_analytics/strategy_evidence_links.parquet",
    )
    queue_parser.add_argument(
        "--families",
        default="data/06_analytics/creative_families.parquet",
    )
    queue_parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    queue_parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
    )
    queue_parser.add_argument(
        "--out",
        default="data/07_knowledge/review",
    )
    queue_parser.add_argument("--include-reviewed", action="store_true")
    queue_parser.add_argument("--show", type=int, default=10)

    decide_parser = subparsers.add_parser(
        "decide",
        help="Write one approve/reject/hold review decision.",
    )
    decide_parser.add_argument("source_type")
    decide_parser.add_argument("source_id")
    decide_parser.add_argument(
        "--decision",
        required=True,
        choices=sorted(ALLOWED_DECISIONS),
    )
    decide_parser.add_argument("--note")
    decide_parser.add_argument("--reviewed-by")
    decide_parser.add_argument("--reviewed-at")
    decide_parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply non-empty decisions from the editable decisions CSV.",
    )
    apply_parser.add_argument(
        "--decisions",
        default=(
            "data/07_knowledge/review/"
            "knowledge_review_decisions.csv"
        ),
    )
    apply_parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
    )
    apply_parser.add_argument("--reviewed-by")

    args = parser.parse_args()
    action = args.action or "queue"
    if action == "queue":
        if args.action is None:
            args = queue_parser.parse_args([])
        _queue_command(args)
    elif action == "decide":
        _decide_command(args)
    elif action == "apply":
        _apply_command(args)
    else:
        raise SystemExit(f"Unknown review action: {action}")


if __name__ == "__main__":
    main()
