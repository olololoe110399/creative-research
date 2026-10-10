from __future__ import annotations

import pandas as pd
import pytest

from creative_research.analysis.build_master import build_master
from creative_research.analysis.validation import validate_master
from creative_research.constants import MASTER_SCHEMA_VERSION


def test_build_master_unifies_slideshow_and_video() -> None:
    slides = pd.DataFrame(
        [
            {
                "account": "acct",
                "post_id": "slide-1",
                "created_at": "2026-01-01T00:00:00Z",
                "views": 100,
                "shares": 5,
                "saves": 10,
                "slide_count": 7,
                "primary_language_code": "en",
                "audience_segment": "nursing_student",
                "content_angle": "study_method",
                "hook_technique": "list_or_number",
                "product_family": "single_product",
                "cta_type": "none",
                "creative_formula": "hook -> value -> product",
                "hook_slide": 1,
                "has_visible_product": True,
                "product_first_slide": 7,
                "has_visible_cta": False,
            }
        ]
    )
    videos = pd.DataFrame(
        [
            {
                "account": "acct",
                "post_id": "video-1",
                "created_at": "2026-01-02T00:00:00Z",
                "views": 200,
                "shares": 8,
                "saves": 12,
                "duration_seconds": 18.0,
                "primary_language_code": "en",
                "audience_segment": "nursing_student",
                "content_angle": "app_tool_recommendation",
                "hook_technique": "direct_address",
                "product_family": "single_product",
                "cta_type": "try_product",
                "creative_formula": "hook -> demo -> cta",
                "hook_start_second": 0.0,
                "hook_end_second": 2.0,
                "hook_spoken_text": "Try this",
                "has_product": True,
                "product_first_second": 8.0,
                "has_explicit_cta": True,
                "cta_second": 16.0,
            }
        ]
    )

    master = build_master(slides, videos)
    assert list(master["content_type"]) == ["slideshow", "video"]
    assert set(master["master_schema_version"]) == {MASTER_SCHEMA_VERSION}
    assert master.loc[0, "source_media_path"] == "data/02_media/tiktok/acct/slide-1"
    assert master.loc[1, "source_media_path"] == "data/03_video_media/acct/video-1"
    assert validate_master(master).ok


def test_build_master_rejects_duplicate_account_post_id() -> None:
    row = {
        "account": "acct",
        "post_id": "same",
        "created_at": "2026-01-01T00:00:00Z",
        "primary_language_code": "en",
        "audience_segment": "general_student",
        "content_angle": "other",
        "hook_technique": "other",
        "product_family": "none",
        "cta_type": "none",
        "creative_formula": "x",
    }
    with pytest.raises(ValueError, match="Duplicate account\\+post_id"):
        build_master(pd.DataFrame([row]), pd.DataFrame([row]))
