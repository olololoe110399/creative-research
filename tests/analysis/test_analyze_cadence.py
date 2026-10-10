from __future__ import annotations

import json

import pandas as pd

from creative_research.analysis.analyze_cadence import build_cadence_tables


def _posts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "post_id": "1",
                "platform": "tiktok",
                "content_type": "slideshow",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "post_uid": "P2",
                "operator_id": "OP1",
                "account_id": "B",
                "account": "b",
                "post_id": "2",
                "platform": "tiktok",
                "content_type": "video",
                "created_at": "2026-01-01T01:00:00Z",
            },
            {
                "post_uid": "P3",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "post_id": "3",
                "platform": "tiktok",
                "content_type": "slideshow",
                "created_at": "2026-01-01T02:00:00Z",
            },
            {
                "post_uid": "P4",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "a",
                "post_id": "4",
                "platform": "tiktok",
                "content_type": "video",
                "created_at": "2026-01-02T00:00:00Z",
            },
        ]
    )


def test_cadence_tracks_account_and_cross_account_operator_chronology() -> None:
    tables = build_cadence_tables(_posts(), timezone="Asia/Ho_Chi_Minh")
    cadence = tables["posting_cadence"].set_index("post_uid")

    assert cadence.loc["P1", "posting_hour_local"] == 7
    assert cadence.loc["P3", "posting_hour_local"] == 9

    assert cadence.loc["P3", "previous_post_uid_account"] == "P1"
    assert cadence.loc["P3", "gap_from_previous_account_hours"] == 2.0

    assert cadence.loc["P3", "previous_post_uid_operator"] == "P2"
    assert cadence.loc["P3", "previous_account_operator"] == "b"
    assert cadence.loc["P3", "gap_from_previous_operator_hours"] == 1.0
    assert cadence.loc["P3", "posts_previous_24h_operator"] == 2

    operator_daily = tables["operator_activity_daily"]
    first_day = operator_daily.loc[operator_daily["local_date"] == "2026-01-01"].iloc[0]
    assert first_day["posts"] == 3
    assert first_day["accounts_active"] == 2
    assert first_day["account_switches"] == 2
    assert first_day["account_switch_rate"] == 1.0


def test_cadence_summaries_capture_historical_baseline() -> None:
    tables = build_cadence_tables(_posts(), timezone="UTC")
    account = tables["account_cadence_summary"].set_index("account_id")
    operator = tables["operator_cadence_summary"].set_index("operator_id")

    assert account.loc["A", "posts"] == 3
    assert account.loc["A", "median_gap_hours"] == 12.0
    assert operator.loc["OP1", "posts"] == 4
    assert operator.loc["OP1", "median_gap_hours"] == 1.0

    top_hours = json.loads(account.loc["A", "top_posting_hours_json"])
    assert top_hours[0]["posts"] >= 1
