from __future__ import annotations

import json

import pandas as pd

from creative_research.analysis.analyze_timeline import build_strategy_timeline_tables


def _posts() -> pd.DataFrame:
    rows = []
    for month, video, start_id in [
        (1, False, 0),
        (2, True, 10),
    ]:
        for index in range(10):
            rows.append(
                {
                    "post_uid": f"P{start_id + index + 1}",
                    "operator_id": "OP1",
                    "account_id": "A" if index < 5 else "B",
                    "account": "a" if index < 5 else "b",
                    "post_id": str(start_id + index + 1),
                    "created_at": f"2026-{month:02d}-{index + 1:02d}T12:00:00Z",
                    "content_type": "video" if video else "slideshow",
                    "views": 100 + index,
                }
            )
    return pd.DataFrame(rows)


def _analysis() -> pd.DataFrame:
    rows = []
    for index in range(20):
        january = index < 10
        rows.append(
            {
                "post_uid": f"P{index + 1}",
                "operator_id": "OP1",
                "account_id": "A" if index % 10 < 5 else "B",
                "account": "a" if index % 10 < 5 else "b",
                "hook_technique": "how_to" if january else "bold_claim",
                "content_angle": "education" if january else "product_demo",
                "content_format": "listicle" if january else None,
                "video_format": None if january else "app_demo",
                "audience_segment": "student",
                "product_placement_style": "none" if january else "immediate",
                "cta_type": "none" if january else "try_product",
                "dominant_visual_type": "notes" if january else "app_screen",
                "has_product": not january,
                "has_cta": not january,
            }
        )
    return pd.DataFrame(rows)


def _performance() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": f"P{index + 1}",
                "views_percentile_account": 0.4 if index < 10 else 0.7,
                "views_percentile_operator": 0.4 if index < 10 else 0.7,
            }
            for index in range(20)
        ]
    )


def _family_members() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": f"P{index + 1}",
                "family_id": f"F{index // 2 + 1}",
                "is_family_origin": index % 2 == 0,
            }
            for index in range(20)
        ]
    )


def _entries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "first_post_uid_on_account": f"P{index + 1}",
                "is_origin_account": index % 2 == 0,
                "entry_order": 1 if index % 2 == 0 else 2,
            }
            for index in range(20)
        ]
    )


def test_timeline_builds_operator_and_account_windows_with_distribution_evidence() -> None:
    tables = build_strategy_timeline_tables(
        _posts(),
        _analysis(),
        _performance(),
        family_members=_family_members(),
        family_entries=_entries(),
        frequency="month",
        timezone="UTC",
        min_posts=5,
        change_threshold=0.20,
    )

    windows = tables["strategy_windows"]
    operator = windows.loc[windows["scope_type"] == "operator"].sort_values("period_id")
    assert len(operator) == 2
    assert operator.iloc[0]["posts"] == 10
    assert operator.iloc[0]["top_content_angle"] == "education"
    assert operator.iloc[1]["top_content_angle"] == "product_demo"
    assert operator.iloc[0]["product_rate"] == 0.0
    assert operator.iloc[1]["product_rate"] == 1.0
    assert operator.iloc[0]["family_origins"] == 5

    distribution = json.loads(operator.iloc[1]["hook_technique_distribution_json"])
    assert distribution == {"bold_claim": 1.0}

    memberships = tables["strategy_window_members"]
    assert len(memberships.loc[memberships["scope_type"] == "operator"]) == 20


def test_timeline_flags_material_adjacent_window_change() -> None:
    tables = build_strategy_timeline_tables(
        _posts(),
        _analysis(),
        _performance(),
        family_members=_family_members(),
        family_entries=_entries(),
        frequency="month",
        timezone="UTC",
        min_posts=5,
        change_threshold=0.20,
    )
    changes = tables["strategy_change_points"]
    operator_change = changes.loc[
        (changes["scope_type"] == "operator") & (changes["scope_id"] == "OP1")
    ].iloc[0]
    assert bool(operator_change["is_change_point"]) is True
    assert operator_change["change_score"] >= 0.20
    changed = json.loads(operator_change["changed_dimensions_json"])
    assert "content_angle" in changed
    assert "hook_technique" in changed
    assert "product_rate" in changed
