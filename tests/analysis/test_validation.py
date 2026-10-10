from __future__ import annotations

import pandas as pd

from creative_research.analysis.validation import validate_master
from creative_research.constants import MASTER_REQUIRED_COLUMNS, MASTER_SCHEMA_VERSION


def valid_row(**overrides):
    row = dict.fromkeys(MASTER_REQUIRED_COLUMNS)
    row.update(
        {
            "master_schema_version": MASTER_SCHEMA_VERSION,
            "content_type": "slideshow",
            "account": "acct",
            "post_id": "1",
            "views": 100,
            "shares": 1,
            "saves": 2,
            "source_media_path": "data/02_media/tiktok/acct/1",
            "primary_language_code": "en",
            "audience_segment": "general_student",
            "content_angle": "study_method",
            "hook_technique": "how_to",
            "product_family": "none",
            "cta_type": "none",
            "creative_formula": "hook -> value",
        }
    )
    row.update(overrides)
    return row


def test_validate_master_accepts_valid_table() -> None:
    report = validate_master(pd.DataFrame([valid_row()]))
    assert report.ok
    assert report.rows == 1


def test_validate_master_catches_duplicates_and_invalid_type() -> None:
    df = pd.DataFrame(
        [
            valid_row(content_type="weird"),
            valid_row(content_type="weird"),
        ]
    )
    report = validate_master(df)
    assert not report.ok
    codes = {issue.code for issue in report.issues}
    assert "duplicate_post" in codes
    assert "invalid_content_type" in codes


def test_validate_legacy_master_has_actionable_error() -> None:
    df = pd.DataFrame([valid_row()]).drop(columns=["master_schema_version"])
    report = validate_master(df)
    assert report.ok is False
    legacy = [issue for issue in report.issues if issue.code == "legacy_master_schema"]
    assert len(legacy) == 1
    assert "rebuild" in legacy[0].message.lower()
    assert "build-master" in legacy[0].message
