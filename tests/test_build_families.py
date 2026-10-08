from __future__ import annotations

import json

import pandas as pd

from creative_research.stages.build_families import (
    _build_features,
    build_creative_family_tables,
    compare_features,
    compare_features_upper_bound,
)


def _posts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"post_uid": "P1", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "1", "created_at": "2026-01-01T00:00:00Z", "content_type": "slideshow"},
            {"post_uid": "P2", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "2", "created_at": "2026-01-03T00:00:00Z", "content_type": "slideshow"},
            {"post_uid": "P3", "operator_id": "OP1", "account_id": "B", "account": "b", "post_id": "3", "created_at": "2026-01-05T00:00:00Z", "content_type": "video"},
            {"post_uid": "P4", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "4", "created_at": "2026-01-06T00:00:00Z", "content_type": "video"},
        ]
    )


def _analysis() -> pd.DataFrame:
    common = {
        "niche": "student study",
        "topic": "study mistakes and active recall",
        "pain_point": "students reread notes but forget",
        "desired_outcome": "remember information for exams",
        "content_angle": "study_method",
        "audience_segment": "college_student",
        "product_family": "none",
        "hook_technique": "list_or_number",
        "hook_replicable_formula": "N study mistakes students should stop making",
        "creative_formula": "mistakes hook -> explain problem -> better method -> proof -> CTA",
    }
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                **common,
                "hook_text": "3 study mistakes that make you forget everything",
                "content_format": "listicle",
                "video_format": None,
            },
            {
                "post_uid": "P2",
                **common,
                "hook_text": "5 study mistakes you need to stop making",
                "content_format": "listicle",
                "video_format": None,
            },
            {
                "post_uid": "P3",
                **common,
                "hook_text": "Stop making these study mistakes before your exam",
                "content_format": None,
                "video_format": "talking_head",
            },
            {
                "post_uid": "P4",
                "niche": "student productivity",
                "topic": "morning routine for productivity",
                "pain_point": "wasting time in the morning",
                "desired_outcome": "start work earlier",
                "content_angle": "productivity",
                "audience_segment": "college_student",
                "product_family": "none",
                "hook_technique": "pov",
                "hook_replicable_formula": "POV morning routine",
                "creative_formula": "morning montage -> routine steps -> ending",
                "hook_text": "POV you finally fixed your morning routine",
                "content_format": None,
                "video_format": "montage",
            },
        ]
    )


def _sequence() -> pd.DataFrame:
    rows = []
    for post_uid in ("P1", "P2", "P3"):
        for position, role in enumerate(("hook", "problem", "value", "proof", "cta"), start=1):
            rows.append({"post_uid": post_uid, "position": position, "role": role})
    for position, role in enumerate(("hook", "context", "value", "ending"), start=1):
        rows.append({"post_uid": "P4", "position": position, "role": role})
    return pd.DataFrame(rows)


def _performance() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"post_uid": "P1", "views_percentile_account": 0.60, "views_percentile_operator": 0.40},
            {"post_uid": "P2", "views_percentile_account": 0.95, "views_percentile_operator": 0.80},
            {"post_uid": "P3", "views_percentile_account": 0.90, "views_percentile_operator": 0.75},
            {"post_uid": "P4", "views_percentile_account": 0.50, "views_percentile_operator": 0.30},
        ]
    )


def test_family_builder_groups_variants_across_accounts_and_formats() -> None:
    tables = build_creative_family_tables(
        _posts(),
        _analysis(),
        _sequence(),
        _performance(),
        threshold=0.68,
        bridge_floor=0.50,
    )

    members = tables["creative_family_members"].set_index("post_uid")
    assert members.loc["P1", "family_id"] == members.loc["P2", "family_id"]
    assert members.loc["P1", "family_id"] == members.loc["P3", "family_id"]
    assert members.loc["P4", "family_id"] != members.loc["P1", "family_id"]

    family_id = members.loc["P1", "family_id"]
    family = tables["creative_families"].set_index("family_id").loc[family_id]
    assert family["member_count"] == 3
    assert family["variant_count"] == 2
    assert family["accounts_count"] == 2
    assert bool(family["cross_account"]) is True
    assert family["origin_account"] == "a"
    assert family["representative_post_uid"] == "P2"
    assert family["lifespan_days"] == 4.0

    reason = json.loads(members.loc["P3", "match_reason_json"])
    assert reason["nearest_score"] >= 0.68
    assert "sequence" in reason["components"]


def test_family_builder_keeps_every_post_with_stable_singleton_family() -> None:
    tables = build_creative_family_tables(
        _posts(),
        _analysis(),
        _sequence(),
        threshold=0.99,
        bridge_floor=0.95,
    )
    members = tables["creative_family_members"]
    assert set(members["post_uid"]) == {"P1", "P2", "P3", "P4"}
    assert len(tables["creative_families"]) == 4
    assert set(tables["creative_families"]["family_confidence"]) == {"singleton"}


def test_unmapped_accounts_do_not_cross_group_without_operator_verification() -> None:
    posts = _posts().iloc[:2].copy()
    posts["operator_id"] = pd.NA
    posts.loc[posts["post_uid"] == "P2", "account_id"] = "B"
    posts.loc[posts["post_uid"] == "P2", "account"] = "b"

    tables = build_creative_family_tables(
        posts,
        _analysis().iloc[:2],
        _sequence().loc[_sequence()["post_uid"].isin(["P1", "P2"])],
        threshold=0.60,
        bridge_floor=0.40,
    )
    members = tables["creative_family_members"].set_index("post_uid")
    assert members.loc["P1", "family_id"] != members.loc["P2", "family_id"]


def test_similarity_upper_bound_never_underestimates_exact_score() -> None:
    features = _build_features(_posts(), _analysis(), _sequence())
    for index, left in enumerate(features):
        for right in features[index + 1 :]:
            exact, _ = compare_features(left, right)
            upper = compare_features_upper_bound(left, right)
            assert exact <= upper + 1e-12


def test_family_builder_reports_pruning_without_changing_membership() -> None:
    stats: dict[str, int] = {}
    tables = build_creative_family_tables(
        _posts(),
        _analysis(),
        _sequence(),
        _performance(),
        threshold=0.99,
        bridge_floor=0.95,
        clustering_stats=stats,
    )
    assert len(tables["creative_families"]) == 4
    assert stats["upper_bound_checks"] > 0
    assert stats["anchor_pruned"] + stats["member_pruned"] > 0
    assert stats["full_comparisons"] < stats["upper_bound_checks"]
