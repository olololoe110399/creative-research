from __future__ import annotations

import pandas as pd

from creative_research.stages.analyze_performance import build_performance_tables


def _posts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"post_uid": "P1", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "1", "platform": "tiktok", "created_at": "2026-01-01T00:00:00Z", "content_type": "slideshow", "views": 10, "likes": 1, "comments": 0, "shares": 0, "saves": 1},
            {"post_uid": "P2", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "2", "platform": "tiktok", "created_at": "2026-01-02T00:00:00Z", "content_type": "slideshow", "views": 20, "likes": 2, "comments": 1, "shares": 1, "saves": 1},
            {"post_uid": "P3", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "3", "platform": "tiktok", "created_at": "2026-01-03T00:00:00Z", "content_type": "video", "views": 30, "likes": 3, "comments": 1, "shares": 1, "saves": 2},
            {"post_uid": "P4", "operator_id": "OP1", "account_id": "A", "account": "a", "post_id": "4", "platform": "tiktok", "created_at": "2026-01-04T00:00:00Z", "content_type": "video", "views": 40, "likes": 4, "comments": 2, "shares": 2, "saves": 3},
            {"post_uid": "P5", "operator_id": "OP1", "account_id": "B", "account": "b", "post_id": "5", "platform": "tiktok", "created_at": "2026-01-05T00:00:00Z", "content_type": "slideshow", "views": 100, "likes": 5, "comments": 3, "shares": 3, "saves": 4},
            {"post_uid": "P6", "operator_id": "OP1", "account_id": "B", "account": "b", "post_id": "6", "platform": "tiktok", "created_at": "2026-01-06T00:00:00Z", "content_type": "slideshow", "views": 200, "likes": 10, "comments": 4, "shares": 4, "saves": 5},
        ]
    )


def test_performance_is_relative_to_account_operator_and_global_baselines() -> None:
    tables = build_performance_tables(_posts())
    perf = tables["post_performance"].set_index("post_uid")

    assert perf.loc["P1", "views_percentile_account"] == 0.25
    assert perf.loc["P4", "views_percentile_account"] == 1.0
    assert perf.loc["P4", "views_vs_account_median"] == 1.6
    assert perf.loc["P4", "views_percentile_operator"] == 4 / 6
    assert perf.loc["P6", "views_percentile_global"] == 1.0
    assert perf.loc["P4", "views_tier_account"] == "top_5"
    assert perf.loc["P1", "views_tier_account"] == "middle_60"
    assert perf.loc["P6", "like_rate_by_view"] == 0.05

    account = tables["account_performance_baselines"].set_index("account_id")
    assert account.loc["A", "median_views"] == 25.0
    assert account.loc["A", "max_views"] == 40.0

    operator = tables["operator_performance_baselines"].set_index("operator_id")
    assert operator.loc["OP1", "posts"] == 6
    assert operator.loc["OP1", "accounts"] == 2


def test_missing_metric_values_remain_missing_instead_of_becoming_zero() -> None:
    posts = _posts()
    posts.loc[0, "views"] = pd.NA
    perf = build_performance_tables(posts)["post_performance"].set_index("post_uid")
    assert pd.isna(perf.loc["P1", "views_percentile_account"])
    assert pd.isna(perf.loc["P1", "views_vs_account_median"])
