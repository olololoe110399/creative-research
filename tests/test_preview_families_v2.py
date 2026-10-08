from __future__ import annotations

import pandas as pd

from creative_research.stages.preview_families_v2 import (
    build_family_v2_preview,
    classify_pair,
)


def _posts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "post_uid": "P2",
                "operator_id": "OP1",
                "account_id": "B",
                "account": "b",
                "created_at": "2026-01-02T00:00:00Z",
            },
            {
                "post_uid": "P3",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "created_at": "2026-01-03T00:00:00Z",
            },
            {
                "post_uid": "P4",
                "operator_id": "OP1",
                "account_id": "C",
                "account": "c",
                "created_at": "2026-01-04T00:00:00Z",
            },
        ]
    )


def _analysis() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "hook_text": "Study schedules for different students",
                "topic": "study schedules for student types",
                "content_angle": "study_method",
                "primary_language_code": "en",
            },
            {
                "post_uid": "P2",
                "hook_text": "Horarios de estudio para diferentes estudiantes",
                "topic": "study schedules for student types",
                "content_angle": "study_method",
                "primary_language_code": "es",
            },
            {
                "post_uid": "P3",
                "hook_text": "Best times to study",
                "topic": "best times to study",
                "content_angle": "study_method",
                "primary_language_code": "en",
            },
            {
                "post_uid": "P4",
                "hook_text": "Study schedules for different students after school",
                "topic": "after school study schedule",
                "content_angle": "study_method",
                "primary_language_code": "en",
            },
        ]
    )


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P2",
                "combined_score": 0.84,
                "structure_score": 0.98,
                "semantic_text_score": 0.31,
                "production_family_score": 0.50,
                "cross_language": True,
                "same_current_family": False,
                "left_hook_text": "Study schedules for different students",
                "right_hook_text": "Horarios de estudio para diferentes estudiantes",
                "left_topic": "study schedules for student types",
                "right_topic": "study schedules for student types",
            },
            {
                "left_post_uid": "P1",
                "right_post_uid": "P3",
                "combined_score": 0.82,
                "structure_score": 1.00,
                "semantic_text_score": 0.25,
                "production_family_score": 0.45,
                "cross_language": False,
                "same_current_family": False,
                "left_hook_text": "Study schedules for different students",
                "right_hook_text": "Best times to study",
                "left_topic": "study schedules for student types",
                "right_topic": "best times to study",
            },
            {
                "left_post_uid": "P1",
                "right_post_uid": "P4",
                "combined_score": 0.77,
                "structure_score": 0.95,
                "semantic_text_score": 0.50,
                "production_family_score": 0.55,
                "cross_language": False,
                "same_current_family": False,
                "left_hook_text": "Study schedules for different students",
                "right_hook_text": "Study schedules for different students after school",
                "left_topic": "study schedules for student types",
                "right_topic": "after school study schedule",
            },
            {
                "left_post_uid": "P2",
                "right_post_uid": "P4",
                "combined_score": 0.83,
                "structure_score": 0.96,
                "semantic_text_score": 0.35,
                "production_family_score": 0.51,
                "cross_language": True,
                "same_current_family": False,
                "left_hook_text": "Horarios de estudio para diferentes estudiantes",
                "right_hook_text": "Study schedules after school",
                "left_topic": "study schedules for student types",
                "right_topic": "after school study schedule",
            },
        ]
    )


def test_language_aware_pair_gates() -> None:
    rows = _pairs().to_dict(orient="records")
    assert classify_pair(rows[0]) == "strong_cross_language"
    assert classify_pair(rows[1]) is None
    assert classify_pair(rows[2]) == "bridge_same_language"
    assert classify_pair(rows[3]) == "strong_cross_language"


def test_preview_requires_strong_seed_and_anchor_bridge() -> None:
    result = build_family_v2_preview(
        _posts(),
        _pairs(),
        _analysis(),
    )
    members = result["members"]
    assert isinstance(members, pd.DataFrame)
    family_by_post = members.set_index("post_uid")["family_id"].to_dict()

    assert family_by_post["P1"] == family_by_post["P2"]
    assert family_by_post["P4"] == family_by_post["P1"]
    assert family_by_post["P3"] != family_by_post["P1"]

    report = result["report"]
    assert report["multi_post_families"] == 1
    assert report["posts_in_multi_post_families"] == 3


def test_current_family_pair_is_always_preserved_as_strong() -> None:
    row = {
        "combined_score": 0.60,
        "structure_score": 0.60,
        "semantic_text_score": 0.10,
        "production_family_score": 0.72,
        "cross_language": False,
        "same_current_family": True,
    }
    assert classify_pair(row) == "strong_current_family"


def test_same_language_taxonomy_match_without_hook_coherence_is_rejected() -> None:
    row = {
        "combined_score": 0.82,
        "structure_score": 0.98,
        "semantic_text_score": 0.40,
        "production_family_score": 0.50,
        "cross_language": False,
        "same_current_family": False,
        "left_hook_text": "Academic failure is my biggest fear",
        "right_hook_text": "Secret tips: listening to Chinese music while studying",
        "left_topic": "effective study methods and exam preparation",
        "right_topic": "secret study tips and learning techniques",
    }
    assert classify_pair(row) is None


def test_same_language_rewrite_with_hook_coherence_is_retained() -> None:
    row = {
        "combined_score": 0.83,
        "structure_score": 0.96,
        "semantic_text_score": 0.44,
        "production_family_score": 0.52,
        "cross_language": False,
        "same_current_family": False,
        "left_hook_text": "Study schedules for different students",
        "right_hook_text": "Study schedule for different student types",
        "left_topic": "study schedules for student types",
        "right_topic": "study schedules for student types",
    }
    assert classify_pair(row) == "strong_same_language"


def test_high_confidence_ai_reject_blocks_deterministic_edge() -> None:
    judgments = pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P2",
                "decision": "different_core_concept",
                "relationship": "thematic_only",
                "confidence": 0.95,
            }
        ]
    )
    result = build_family_v2_preview(
        _posts(),
        _pairs(),
        _analysis(),
        judgments,
    )
    members = result["members"]
    assert isinstance(members, pd.DataFrame)
    family_by_post = members.set_index("post_uid")["family_id"].to_dict()
    assert family_by_post["P1"] != family_by_post["P2"]
    assert result["report"]["ai_override_counts"]["reject_ai_different"] == 1


def test_high_confidence_ai_accept_can_create_strong_edge() -> None:
    pairs = _pairs().copy()
    pairs.loc[
        pairs["right_post_uid"].eq("P3"),
        ["combined_score", "structure_score", "semantic_text_score"],
    ] = [0.60, 0.60, 0.20]
    judgments = pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P3",
                "decision": "same_core_concept",
                "relationship": "hook_variant",
                "confidence": 0.92,
            }
        ]
    )
    result = build_family_v2_preview(
        _posts(),
        pairs,
        _analysis(),
        judgments,
    )
    members = result["members"]
    assert isinstance(members, pd.DataFrame)
    family_by_post = members.set_index("post_uid")["family_id"].to_dict()
    assert family_by_post["P1"] == family_by_post["P3"]
    assert result["report"]["gate_counts"]["strong_ai_core"] == 1


def test_low_confidence_ai_falls_back_to_deterministic_gate() -> None:
    judgments = pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P2",
                "decision": "different_core_concept",
                "relationship": "thematic_only",
                "confidence": 0.50,
            }
        ]
    )
    result = build_family_v2_preview(
        _posts(),
        _pairs(),
        _analysis(),
        judgments,
    )
    members = result["members"]
    assert isinstance(members, pd.DataFrame)
    family_by_post = members.set_index("post_uid")["family_id"].to_dict()
    assert family_by_post["P1"] == family_by_post["P2"]


def test_ai_execution_variant_does_not_seed_core_family() -> None:
    pairs = _pairs().copy()
    pairs.loc[
        pairs["right_post_uid"].eq("P3"),
        ["combined_score", "structure_score", "semantic_text_score"],
    ] = [0.60, 0.60, 0.20]
    judgments = pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P3",
                "decision": "same_core_concept",
                "relationship": "execution_variant",
                "confidence": 0.95,
            }
        ]
    )
    result = build_family_v2_preview(
        _posts(),
        pairs,
        _analysis(),
        judgments,
    )
    members = result["members"]
    assert isinstance(members, pd.DataFrame)
    family_by_post = members.set_index("post_uid")["family_id"].to_dict()
    assert family_by_post["P1"] != family_by_post["P3"]
    assert (
        result["report"]["ai_override_counts"]["defer_ai_execution"]
        == 1
    )


def test_ai_execution_variant_can_fall_back_to_deterministic_edge() -> None:
    judgments = pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P2",
                "decision": "same_core_concept",
                "relationship": "execution_variant",
                "confidence": 0.95,
            }
        ]
    )
    result = build_family_v2_preview(
        _posts(),
        _pairs(),
        _analysis(),
        judgments,
    )
    members = result["members"]
    assert isinstance(members, pd.DataFrame)
    family_by_post = members.set_index("post_uid")["family_id"].to_dict()
    assert family_by_post["P1"] == family_by_post["P2"]
    assert (
        result["report"]["ai_override_counts"]["defer_ai_execution"]
        == 1
    )
