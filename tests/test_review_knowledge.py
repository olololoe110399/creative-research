from __future__ import annotations

import json

import pandas as pd

from creative_research.stages.review_knowledge import build_review_queue


def _catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "knowledge_id": "KSTR-1",
                "knowledge_type": "strategy",
                "subtype": "operator_explore_propagate_model",
                "scope_type": "operator",
                "scope_id": "OP1",
                "title": "Explore propagate model",
                "statement": "Operator separates origin and reuse.",
                "confidence_score": 0.84,
                "knowledge_status": "review_candidate",
                "source_type": "hypothesis",
                "source_ids_json": json.dumps(["STR-1"]),
                "source_pattern_ids_json": json.dumps(["PAT-A", "PAT-B"]),
                "source_family_ids_json": json.dumps([]),
                "exceptions_json": json.dumps(["Alternative."]),
                "review_source_type": "hypothesis",
                "review_source_id": "STR-1",
            },
            {
                "knowledge_id": "KLES-1",
                "knowledge_type": "lesson",
                "subtype": "operator_explore_propagate_model",
                "scope_type": "operator",
                "scope_id": "OP1",
                "title": "Lesson: explore propagate model",
                "statement": "Operator separates origin and reuse.",
                "confidence_score": 0.84,
                "knowledge_status": "review_candidate",
                "source_type": "hypothesis",
                "source_ids_json": json.dumps(["STR-1"]),
                "source_pattern_ids_json": json.dumps(["PAT-A", "PAT-B"]),
                "source_family_ids_json": json.dumps([]),
                "exceptions_json": json.dumps(["Alternative."]),
                "review_source_type": "hypothesis",
                "review_source_id": "STR-1",
            },
            {
                "knowledge_id": "KTPL-1",
                "knowledge_type": "template",
                "subtype": "creative_family_structure",
                "scope_type": "operator",
                "scope_id": "OP1",
                "title": "Study schedules template",
                "statement": "Reusable structure across six executions.",
                "confidence_score": 0.80,
                "knowledge_status": "promoted",
                "source_type": "family",
                "source_ids_json": json.dumps(["FAM-1"]),
                "source_pattern_ids_json": json.dumps([]),
                "source_family_ids_json": json.dumps(["FAM-1"]),
                "exceptions_json": json.dumps([]),
                "review_source_type": "family",
                "review_source_id": "FAM-1",
            },
            {
                "knowledge_id": "KSTR-2",
                "knowledge_type": "strategy",
                "subtype": "temporal_strategy_shift",
                "scope_type": "operator",
                "scope_id": "OP1",
                "title": "Temporal shift",
                "statement": "A material shift is observed.",
                "confidence_score": 0.70,
                "knowledge_status": "review_candidate",
                "source_type": "hypothesis",
                "source_ids_json": json.dumps(["STR-2"]),
                "source_pattern_ids_json": json.dumps(["PAT-T"]),
                "source_family_ids_json": json.dumps([]),
                "exceptions_json": json.dumps(["Seasonality."]),
                "review_source_type": "hypothesis",
                "review_source_id": "STR-2",
            },
            {
                "knowledge_id": "KSTR-3",
                "knowledge_type": "strategy",
                "subtype": "account_reuse_receiver",
                "scope_type": "account",
                "scope_id": "A",
                "title": "Approved receiver",
                "statement": "Already reviewed.",
                "confidence_score": 0.82,
                "knowledge_status": "approved",
                "source_type": "hypothesis",
                "source_ids_json": json.dumps(["STR-3"]),
                "source_pattern_ids_json": json.dumps(["PAT-R"]),
                "source_family_ids_json": json.dumps([]),
                "exceptions_json": json.dumps([]),
                "review_source_type": "hypothesis",
                "review_source_id": "STR-3",
            },
        ]
    )


def _evidence() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "knowledge_id": "KSTR-1",
                "pattern_id": "PAT-A",
                "post_uid": "P1",
                "family_id": "F1",
            },
            {
                "knowledge_id": "KLES-1",
                "pattern_id": "PAT-B",
                "post_uid": "P2",
                "family_id": "F2",
            },
            {
                "knowledge_id": "KTPL-1",
                "pattern_id": None,
                "post_uid": "P3",
                "family_id": "FAM-1",
            },
        ]
    )


def test_review_queue_collapses_duplicate_knowledge_items_by_source() -> None:
    queue, meta = build_review_queue(_catalog(), _evidence())

    assert meta["unresolved_review_targets"] == 0
    assert len(queue) == 3

    model = queue.loc[
        queue["review_source_id"].eq("STR-1")
    ].iloc[0]
    assert json.loads(model["knowledge_types_json"]) == [
        "lesson",
        "strategy",
    ]
    assert model["evidence_post_count"] == 2
    assert model["priority_tier"] == 1

    promoted = queue.loc[
        queue["review_source_id"].eq("FAM-1")
    ].iloc[0]
    assert promoted["priority_tier"] == 1
    assert promoted["priority_reason"] == "audit_auto_promoted"

    temporal = queue.loc[
        queue["review_source_id"].eq("STR-2")
    ].iloc[0]
    assert temporal["priority_tier"] == 3
    assert "STR-3" not in set(queue["review_source_id"])


def test_review_queue_can_include_already_reviewed_sources() -> None:
    queue, _ = build_review_queue(
        _catalog(),
        _evidence(),
        include_reviewed=True,
    )
    reviewed = queue.loc[
        queue["review_source_id"].eq("STR-3")
    ]
    assert len(reviewed) == 1
