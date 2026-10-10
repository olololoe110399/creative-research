from __future__ import annotations

import pandas as pd

from creative_research.analysis.calibrate_families import (
    calibrate_family_pairs,
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
                "content_type": "slideshow",
                "post_id": "1",
            },
            {
                "post_uid": "P2",
                "operator_id": "OP1",
                "account_id": "B",
                "account": "b",
                "created_at": "2026-01-02T00:00:00Z",
                "content_type": "slideshow",
                "post_id": "2",
            },
            {
                "post_uid": "P3",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "created_at": "2026-01-03T00:00:00Z",
                "content_type": "video",
                "post_id": "3",
            },
        ]
    )


def _analysis() -> pd.DataFrame:
    common = {
        "audience_segment": "college_student",
        "content_angle": "study_method",
        "value_type": "how_to",
        "hook_technique": "how_to",
        "product_family": "none",
        "product_placement_style": "none",
        "cta_type": "save",
        "dominant_visual_type": "notes_or_document",
        "creative_formula": "hook -> explain method -> proof -> CTA",
        "content_format": "tutorial",
        "video_format": None,
    }
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                **common,
                "primary_language_code": "en",
                "niche": "student study",
                "topic": "study smarter not harder",
                "pain_point": "studying for too long",
                "desired_outcome": "study efficiently",
                "hook_text": "How to study smarter, not harder",
                "hook_replicable_formula": "How to X smarter, not harder",
            },
            {
                "post_uid": "P2",
                **common,
                "primary_language_code": "es",
                "niche": "student study",
                "topic": "study smarter not harder",
                "pain_point": "studying for too long",
                "desired_outcome": "study efficiently",
                "hook_text": "Cómo estudiar de forma más inteligente y no más duro",
                "hook_replicable_formula": "How to X smarter, not harder",
            },
            {
                "post_uid": "P3",
                "primary_language_code": "en",
                "audience_segment": "college_student",
                "niche": "student productivity",
                "topic": "morning routine",
                "content_angle": "productivity",
                "value_type": "relatable_story",
                "pain_point": "wasting mornings",
                "desired_outcome": "start earlier",
                "hook_text": "My 5am routine",
                "hook_technique": "pov",
                "hook_replicable_formula": "POV + routine",
                "creative_formula": "hook -> routine -> ending",
                "content_format": None,
                "video_format": "montage",
                "product_family": "none",
                "product_placement_style": "none",
                "cta_type": "none",
                "dominant_visual_type": "real_person_lifestyle",
            },
        ]
    )


def _sequence() -> pd.DataFrame:
    rows = []
    for post_uid in ("P1", "P2"):
        rows.extend(
            [
                {
                    "post_uid": post_uid,
                    "position": 1,
                    "role": "hook",
                    "visual_type": "notes_or_document",
                    "visual_description": "student notes and study desk",
                },
                {
                    "post_uid": post_uid,
                    "position": 2,
                    "role": "study_tip",
                    "visual_type": "notes_or_document",
                    "visual_description": "study method explanation",
                },
                {
                    "post_uid": post_uid,
                    "position": 3,
                    "role": "cta",
                    "visual_type": "notes_or_document",
                    "visual_description": "save reminder",
                },
            ]
        )
    rows.extend(
        [
            {
                "post_uid": "P3",
                "position": 1,
                "role": "hook",
                "visual_type": "real_person_lifestyle",
                "visual_description": "morning routine",
            },
            {
                "post_uid": "P3",
                "position": 2,
                "role": "body",
                "visual_type": "real_person_lifestyle",
                "visual_description": "coffee and desk",
            },
        ]
    )
    return pd.DataFrame(rows)


def test_calibration_surfaces_cross_language_structural_variant() -> None:
    pairs, report = calibrate_family_pairs(
        _posts(),
        _analysis(),
        _sequence(),
        min_structure=0.40,
        min_combined=0.50,
        max_pairs=100,
    )
    pair = pairs.loc[
        (pairs["left_post_uid"].eq("P1") & pairs["right_post_uid"].eq("P2"))
        | (pairs["left_post_uid"].eq("P2") & pairs["right_post_uid"].eq("P1"))
    ].iloc[0]

    assert bool(pair["cross_language"]) is True
    assert pair["structure_score"] > 0.95
    assert pair["combined_score"] > 0.80
    assert report["theoretical_operator_pairs"] == 3
    assert report["candidate_pairs_generated"] >= 1
    assert report["retained_cross_language_pairs"] >= 1


def test_calibration_separates_unrelated_structure() -> None:
    pairs, _ = calibrate_family_pairs(
        _posts(),
        _analysis(),
        _sequence(),
        min_structure=0.40,
        min_combined=0.50,
        max_pairs=100,
    )
    p3_pairs = pairs.loc[pairs["left_post_uid"].eq("P3") | pairs["right_post_uid"].eq("P3")]
    assert p3_pairs.empty


def test_calibration_blocker_recovers_existing_family_pairs() -> None:
    members = pd.DataFrame(
        [
            {"post_uid": "P1", "family_id": "F1"},
            {"post_uid": "P2", "family_id": "F1"},
            {"post_uid": "P3", "family_id": "F2"},
        ]
    )
    _, report = calibrate_family_pairs(
        _posts(),
        _analysis(),
        _sequence(),
        members,
        min_structure=0.40,
        min_combined=0.50,
        max_pairs=100,
    )
    assert report["existing_family_pairs"] == 1
    assert report["existing_family_pairs_recovered"] == 1
    assert report["existing_family_pair_recall"] == 1.0
