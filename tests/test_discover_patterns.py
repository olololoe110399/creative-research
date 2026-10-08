from __future__ import annotations

import json

import pandas as pd

from creative_research.stages.discover_patterns import build_pattern_tables


def _analysis() -> pd.DataFrame:
    rows = []
    for index in range(12):
        strong = index < 6
        rows.append(
            {
                "post_uid": f"P{index + 1}",
                "operator_id": "OP1",
                "account_id": "A" if index < 8 else "B",
                "account": "a" if index < 8 else "b",
                "hook_technique": "bold_claim" if strong else "question",
                "content_angle": "education",
                "content_format": "listicle",
                "video_format": None,
                "product_placement_style": "none",
                "cta_type": "save",
                "dominant_visual_type": "notes",
                "audience_segment": "student",
            }
        )
    return pd.DataFrame(rows)


def _performance() -> pd.DataFrame:
    rows = []
    for index in range(12):
        strong = index < 6
        rows.append(
            {
                "post_uid": f"P{index + 1}",
                "operator_id": "OP1",
                "account_id": "A" if index < 8 else "B",
                "views_percentile_account": 0.9 if strong else 0.2,
                "views_percentile_operator": 0.9 if strong else 0.2,
            }
        )
    return pd.DataFrame(rows)


def _cadence() -> pd.DataFrame:
    rows = []
    for index in range(12):
        strong = index < 6
        rows.append(
            {
                "post_uid": f"P{index + 1}",
                "gap_to_next_account_hours": 12.0 if strong else 3.0,
                "gap_to_next_operator_hours": 10.0 if strong else 2.0,
            }
        )
    return pd.DataFrame(rows)


def _propagation() -> pd.DataFrame:
    rows = []
    for index in range(6):
        changed = ["hook_text"]
        preserved = ["content_angle", "creative_formula", "sequence_roles"]
        if index < 5:
            changed.append("hook_technique")
        else:
            preserved.append("hook_technique")
        rows.append(
            {
                "family_id": f"F{index + 1}",
                "operator_id": "OP1",
                "target_first_post_uid": f"T{index + 1}",
                "target_account_id": "B",
                "changed_dimensions_json": json.dumps(changed),
                "preserved_dimensions_json": json.dumps(preserved),
            }
        )
    return pd.DataFrame(rows)


def _families() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "family_id": f"F{index + 1}",
                "operator_id": "OP1",
                "member_count": 2 if index < 4 else 1,
                "cross_account": index < 3,
                "lifespan_days": float(index + 1),
            }
            for index in range(6)
        ]
    )


def _members() -> pd.DataFrame:
    rows = []
    for index in range(6):
        rows.append({"family_id": f"F{index + 1}", "post_uid": f"P{index + 1}"})
    return pd.DataFrame(rows)


def _role_evidence() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "operator_id": "OP1",
                "account_id": "A",
                "descriptive_profile": "originator_leaning",
                "evidence_strength": "medium",
                "propagated_origin_families": 4,
                "imported_families": 1,
                "families_participated": 6,
                "family_origin_rate": 0.8,
                "imported_family_rate": 0.2,
                "outbound_propagation_rate": 0.75,
                "cross_account_participation_rate": 0.6,
                "cross_account_flow_observations": 5,
                "cross_account_origin_rate": 0.8,
                "cross_account_import_rate": 0.2,
                "originator_signal": 0.78,
                "receiver_signal": 0.2,
                "amplifier_signal": 0.5,
            }
        ]
    )


def _changes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scope_type": "operator",
                "scope_id": "OP1",
                "operator_id": "OP1",
                "previous_period_id": "2026-01",
                "current_period_id": "2026-02",
                "is_change_point": True,
                "change_score": 0.6,
                "changed_dimensions_json": json.dumps(["hook_technique", "product_rate"]),
                "dimension_tvd_json": json.dumps({"hook_technique": 1.0}),
                "scalar_changes_json": json.dumps({"product_rate": 0.7}),
                "previous_posts": 6,
                "current_posts": 6,
            }
        ]
    )


def _window_members() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scope_type": "operator",
                "scope_id": "OP1",
                "period_id": "2026-01" if index < 6 else "2026-02",
                "post_uid": f"P{index + 1}",
            }
            for index in range(12)
        ]
    )


def test_pattern_engine_discovers_multiple_pattern_classes_with_evidence_links() -> None:
    tables = build_pattern_tables(
        _analysis(),
        _performance(),
        _cadence(),
        _families(),
        _members(),
        _propagation(),
        _role_evidence(),
        _changes(),
        _window_members(),
        min_sample=5,
        min_performance_effect=0.10,
        min_cadence_effect=0.25,
        propagation_dominant_rate=0.70,
    )

    patterns = tables["patterns"]
    types = set(patterns["pattern_type"])
    assert "creative_dimension_performance" in types
    assert "cadence_after_performance" in types
    assert "propagation_dimension_behavior" in types
    assert "family_reuse_baseline" in types
    assert "account_flow_profile" in types
    assert "strategy_change_point" in types

    bold = patterns.loc[
        (patterns["pattern_type"] == "creative_dimension_performance")
        & patterns["title"].str.contains("hook_technique=bold_claim")
    ].iloc[0]
    assert bold["effect_size"] > 0

    propagation = patterns.loc[
        (patterns["pattern_type"] == "propagation_dimension_behavior")
        & patterns["title"].str.contains("hook_technique")
    ].iloc[0]
    assert propagation["support_rate"] == 5 / 6

    links = tables["pattern_evidence_links"]
    assert links["pattern_id"].isin(patterns["pattern_id"]).all()
    assert links["post_uid"].notna().any()


def test_pattern_engine_does_not_emit_small_performance_groups() -> None:
    tables = build_pattern_tables(
        _analysis().head(4),
        _performance().head(4),
        min_sample=5,
    )
    patterns = tables["patterns"]
    assert (
        patterns.empty
        or "creative_dimension_performance"
        not in set(patterns["pattern_type"])
    )



def test_reuse_pattern_conditions_cross_account_share_on_repeated_families() -> None:
    families = pd.DataFrame(
        [
            {
                "family_id": f"F{index}",
                "operator_id": "OP1",
                "member_count": 2 if index < 6 else 1,
                "cross_account": index < 5,
                "lifespan_days": float(index),
            }
            for index in range(10)
        ]
    )
    members = pd.DataFrame(
        [
            {"family_id": f"F{index}", "post_uid": f"P{index}"}
            for index in range(10)
        ]
    )
    tables = build_pattern_tables(
        families=families,
        family_members=members,
        min_sample=5,
    )
    patterns = tables["patterns"]
    conditional = patterns.loc[
        patterns["pattern_type"].eq("cross_account_reuse_conditional")
    ].iloc[0]
    metrics = json.loads(conditional["metrics_json"])
    assert metrics["multi_post_families"] == 6
    assert metrics["cross_account_repeated_families"] == 5
    assert metrics["cross_account_share_of_repeated"] == 5 / 6
    assert conditional["sample_size"] == 6
    assert conditional["support_rate"] == 5 / 6

    links = tables["pattern_evidence_links"].loc[
        tables["pattern_evidence_links"]["pattern_id"].eq(
            conditional["pattern_id"]
        )
    ]
    assert set(links["family_id"]) == {f"F{i}" for i in range(6)}
