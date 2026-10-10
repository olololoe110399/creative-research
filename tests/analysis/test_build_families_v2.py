from __future__ import annotations

import pandas as pd

from creative_research.analysis.build_families_v2 import (
    ACTIVE_AI_PROMPT_VERSION,
    ACTIVE_AI_SCHEMA_VERSION,
    FAMILY_MODEL_V2,
    FAMILY_SCHEMA_VERSION_V2,
    _active_ai_judgments,
    build_creative_family_tables_v2,
)


def _posts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "post_id": "1",
                "created_at": "2026-01-01T00:00:00Z",
                "content_type": "slideshow",
            },
            {
                "post_uid": "P2",
                "operator_id": "OP1",
                "account_id": "B",
                "account": "b",
                "post_id": "2",
                "created_at": "2026-01-03T00:00:00Z",
                "content_type": "slideshow",
            },
            {
                "post_uid": "P3",
                "operator_id": "OP1",
                "account_id": "C",
                "account": "c",
                "post_id": "3",
                "created_at": "2026-01-05T00:00:00Z",
                "content_type": "video",
            },
            {
                "post_uid": "P4",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "post_id": "4",
                "created_at": "2026-01-06T00:00:00Z",
                "content_type": "video",
            },
        ]
    )


def _analysis() -> pd.DataFrame:
    common = {
        "primary_language_code": "en",
        "niche": "student study",
        "topic": "study mistakes and active recall",
        "value_type": "how_to",
        "pain_point": "students reread notes but forget",
        "desired_outcome": "remember information for exams",
        "content_angle": "study_method",
        "audience_segment": "college_student",
        "product_family": "none",
        "product_placement_style": "none",
        "cta_type": "save",
        "dominant_visual_type": "notes_or_document",
        "hook_technique": "list_or_number",
        "hook_replicable_formula": "N study mistakes students should stop making",
        "creative_formula": "mistakes hook -> better method -> proof -> CTA",
    }
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                **common,
                "hook_text": "3 study mistakes that make you forget everything",
                "content_format": "listicle",
            },
            {
                "post_uid": "P2",
                **common,
                "hook_text": "5 study mistakes you need to stop making",
                "content_format": "listicle",
            },
            {
                "post_uid": "P3",
                **common,
                "hook_text": "Stop making these study mistakes before your exam",
                "video_format": "talking_head",
            },
            {
                "post_uid": "P4",
                "primary_language_code": "en",
                "niche": "student productivity",
                "topic": "morning routine for productivity",
                "value_type": "routine",
                "pain_point": "wasting time in the morning",
                "desired_outcome": "start work earlier",
                "content_angle": "productivity",
                "audience_segment": "college_student",
                "product_family": "none",
                "product_placement_style": "none",
                "cta_type": "none",
                "dominant_visual_type": "lifestyle",
                "hook_technique": "pov",
                "hook_replicable_formula": "POV morning routine",
                "creative_formula": "morning montage -> routine steps",
                "hook_text": "POV you finally fixed your morning routine",
                "video_format": "montage",
            },
        ]
    )


def _sequence() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for post_uid in ("P1", "P2", "P3"):
        for position, role in enumerate(
            ("hook", "problem", "value", "proof", "cta"),
            start=1,
        ):
            rows.append(
                {
                    "post_uid": post_uid,
                    "position": position,
                    "role": role,
                    "visual_type": "notes",
                    "visual_description": role,
                }
            )
    for position, role in enumerate(
        ("hook", "context", "value", "ending"),
        start=1,
    ):
        rows.append(
            {
                "post_uid": "P4",
                "position": position,
                "role": role,
                "visual_type": "lifestyle",
                "visual_description": role,
            }
        )
    return pd.DataFrame(rows)


def _performance() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "views_percentile_account": 0.60,
                "views_percentile_operator": 0.40,
            },
            {
                "post_uid": "P2",
                "views_percentile_account": 0.95,
                "views_percentile_operator": 0.80,
            },
            {
                "post_uid": "P3",
                "views_percentile_account": 0.90,
                "views_percentile_operator": 0.75,
            },
            {
                "post_uid": "P4",
                "views_percentile_account": 0.50,
                "views_percentile_operator": 0.30,
            },
        ]
    )


def test_production_v2_preserves_downstream_schema_and_lineage() -> None:
    tables, meta = build_creative_family_tables_v2(
        _posts(),
        _analysis(),
        _sequence(),
        _performance(),
    )

    families = tables["creative_families"]
    member_table = tables["creative_family_members"]
    members = member_table.set_index("post_uid")

    assert set(members.index) == {"P1", "P2", "P3", "P4"}
    assert members.loc["P1", "family_id"] == members.loc["P2", "family_id"]
    assert members.loc["P1", "family_id"] == members.loc["P3", "family_id"]
    assert members.loc["P4", "family_id"] != members.loc["P1", "family_id"]

    assert set(families["family_schema_version"]) == {FAMILY_SCHEMA_VERSION_V2}
    assert set(members["family_schema_version"]) == {FAMILY_SCHEMA_VERSION_V2}
    assert set(families["family_model"]) == {FAMILY_MODEL_V2}
    assert all(str(value).startswith("FAM-") for value in families["family_id"])

    required_member_columns = {
        "family_id",
        "operator_id",
        "post_uid",
        "account_id",
        "account",
        "post_id",
        "created_at",
        "content_type",
        "family_member_index",
        "is_family_origin",
        "family_origin_post_uid",
        "days_since_family_origin",
        "match_score_to_origin",
        "match_score_to_nearest_member",
        "nearest_member_post_uid",
        "match_reason_json",
        "topic",
        "content_angle",
        "hook_text",
        "hook_replicable_formula",
        "creative_formula",
        "sequence_roles_json",
        "views_percentile_account",
        "views_percentile_operator",
    }
    assert required_member_columns.issubset(member_table.columns)
    assert meta["family_schema_version"] == FAMILY_SCHEMA_VERSION_V2
    assert meta["preview"]["posts"] == 4


def test_production_v2_filters_stale_ai_judgment_versions() -> None:
    judgments = pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P2",
                "judge_schema_version": ACTIVE_AI_SCHEMA_VERSION,
                "prompt_version": ACTIVE_AI_PROMPT_VERSION,
                "decision": "different_core_concept",
                "relationship": "template_variant",
                "confidence": 0.95,
            },
            {
                "left_post_uid": "P2",
                "right_post_uid": "P3",
                "judge_schema_version": "family-ai-judge-v1",
                "prompt_version": "family-ai-judge-prompt-v1",
                "decision": "different_core_concept",
                "relationship": "template_variant",
                "confidence": 0.99,
            },
        ]
    )
    active, stats = _active_ai_judgments(judgments)
    assert active is not None
    assert len(active) == 1
    assert active.iloc[0]["left_post_uid"] == "P1"
    assert stats == {
        "ai_rows_supplied": 2,
        "ai_rows_active": 1,
        "ai_rows_incompatible": 1,
    }
