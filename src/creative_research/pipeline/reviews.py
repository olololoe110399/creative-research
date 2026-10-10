#!/usr/bin/env python3
"""Human review workflow for evidence-derived knowledge.

This stage never changes inference logic and never auto-approves knowledge. It:
- rebuilds current knowledge candidates in memory from durable analytics;
- collapses duplicate strategy/lesson representations to one source-level review target;
- writes a prioritized human review queue and editable decisions CSV;
- applies approve/reject/hold decisions to local knowledge_reviews.toml.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from creative_research.analysis.promote_knowledge import build_knowledge_tables
from creative_research.analysis.review_knowledge import (
    REVIEW_WORKFLOW_SCHEMA_VERSION,
    build_review_queue,
)
from creative_research.infrastructure.knowledge_reviews import (
    ALLOWED_DECISIONS,
    KnowledgeReview,
    load_knowledge_reviews,
    upsert_knowledge_reviews,
)
from creative_research.infrastructure.paths import project_root
from creative_research.infrastructure.storage import atomic_output, read_table, write_csv
from creative_research.infrastructure.storage import write_text as atomic_write_text


@dataclass(frozen=True, slots=True)
class ReviewQueueOptions:
    hypotheses: str
    strategy_evidence: str
    families: str
    family_members: str
    reviews: str
    out: str
    include_reviewed: bool
    show: int


@dataclass(frozen=True, slots=True)
class ReviewDecisionOptions:
    source_type: str
    source_id: str
    decision: str
    note: str | None
    reviewed_by: str | None
    reviewed_at: str | None
    reviews: str


@dataclass(frozen=True, slots=True)
class ReviewImportOptions:
    decisions: str
    reviews: str
    reviewed_by: str | None


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


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
                (f"- Target: {row['review_source_type']}:{row['review_source_id']}"),
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
        read_table(strategy_evidence_path) if strategy_evidence_path.exists() else None
    )
    families = read_table(families_path) if families_path.exists() else None
    family_members = read_table(family_members_path) if family_members_path.exists() else None
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


def queue_reviews(options: ReviewQueueOptions) -> None:
    root = project_root().resolve()
    hypotheses_path = _resolve(root, options.hypotheses)
    strategy_evidence_path = _resolve(root, options.strategy_evidence)
    families_path = _resolve(root, options.families)
    family_members_path = _resolve(root, options.family_members)
    reviews_path = _resolve(root, options.reviews) if options.reviews else None
    out_dir = _resolve(root, options.out)
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
        include_reviewed=options.include_reviewed,
    )

    queue_csv = out_dir / "knowledge_review_queue.csv"
    queue_jsonl = out_dir / "knowledge_review_queue.jsonl"
    decisions_csv = out_dir / "knowledge_review_decisions.csv"
    packet_md = out_dir / "knowledge_review_packet.md"
    report_json = out_dir / "knowledge_review_report.json"

    write_csv(queue_csv, queue, index=False, encoding="utf-8-sig")
    with atomic_output(queue_jsonl) as temporary:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in queue.to_dict(orient="records"):
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

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
        if column not in {"decision", "note", "reviewed_by", "reviewed_at"}
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
    write_csv(decisions_csv, decisions, index=False, encoding="utf-8-sig")
    atomic_write_text(packet_md, _review_packet(queue))

    catalog = tables["knowledge_catalog"]
    tier_counts = (
        {
            str(int(key)): int(value)
            for key, value in queue["priority_tier"].value_counts().sort_index().items()
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
            str(reviews_path) if reviews_path is not None and reviews_path.exists() else None
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
            ("Tier 1 prioritizes operating-model/account-role evidence and auto-promoted items."),
            ("Temporal strategy shifts are intentionally reviewed after operating-model evidence."),
        ],
    }
    atomic_write_text(report_json, json.dumps(report, ensure_ascii=False, indent=2))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not queue.empty:
        print("\nTop review targets:")
        for row in queue.head(max(1, options.show)).to_dict(orient="records"):
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


def _build_review(
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
        raise ValueError("review_source_type must be hypothesis, family, or playbook_sources")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError("decision must be one of " + ", ".join(sorted(ALLOWED_DECISIONS)))
    return KnowledgeReview(
        source_type=source_type,
        source_id=source_id,
        decision=decision,
        note=note.strip() if note and note.strip() else None,
        reviewed_by=(reviewed_by.strip() if reviewed_by and reviewed_by.strip() else None),
        reviewed_at=(
            reviewed_at.strip()
            if reviewed_at and reviewed_at.strip()
            else datetime.now(UTC).isoformat()
        ),
    )


def decide_review(options: ReviewDecisionOptions) -> None:
    root = project_root().resolve()
    reviews_path = _resolve(root, options.reviews)
    review = _build_review(
        source_type=options.source_type,
        source_id=options.source_id,
        decision=options.decision,
        note=options.note,
        reviewed_by=options.reviewed_by,
        reviewed_at=options.reviewed_at,
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
        f"--reviews {options.reviews}"
    )


def apply_reviews(options: ReviewImportOptions) -> None:
    root = project_root().resolve()
    decisions_path = _resolve(root, options.decisions)
    reviews_path = _resolve(root, options.reviews)
    frame = pd.read_csv(decisions_path, dtype=str).fillna("")
    required = {"review_source_type", "review_source_id", "decision"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("decisions CSV missing columns: " + ", ".join(missing))

    incoming: list[KnowledgeReview] = []
    for row in frame.to_dict(orient="records"):
        decision = str(row.get("decision") or "").strip()
        if not decision:
            continue
        incoming.append(
            _build_review(
                source_type=str(row.get("review_source_type") or ""),
                source_id=str(row.get("review_source_id") or ""),
                decision=decision,
                note=str(row.get("note") or ""),
                reviewed_by=(str(row.get("reviewed_by") or "") or options.reviewed_by),
                reviewed_at=str(row.get("reviewed_at") or ""),
            )
        )

    if not incoming:
        print("No non-empty decisions found; reviews file was not changed.")
        return

    reviews = upsert_knowledge_reviews(reviews_path, incoming)
    counts = (
        pd.Series(
            [review.decision for review in incoming],
            dtype="object",
        )
        .value_counts()
        .to_dict()
    )
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
        f"--reviews {options.reviews}"
    )
