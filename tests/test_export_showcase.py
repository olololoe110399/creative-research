from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.stages.export_showcase import export_showcase


def sample_master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "account": "real_creator_a",
                "post_id": "111",
                "url": "https://example.test/a/111",
                "content_type": "slideshow",
                "created_at": "2026-01-01T00:00:00Z",
                "views": 100,
                "likes": 20,
                "comments": 2,
                "shares": 5,
                "saves": 10,
                "share_rate": 0.05,
                "save_rate": 0.10,
                "account_views_pct": 0.80,
                "global_views_pct": 0.50,
                "primary_language_code": "en",
                "audience_segment": "general_student",
                "content_angle": "study_method",
                "value_type": "how_to",
                "hook_technique": "list_or_number",
                "content_format": "listicle",
                "dominant_visual_type": "notes_or_document",
                "product_family": "single_product",
                "product_placement_style": "late_reveal",
                "cta_type": "none",
                "slide_count": 7,
                "hook_text": "Seven things to learn",
                "creative_formula": "hook -> value -> product",
                "analysis_json": "SECRET RAW ANALYSIS",
                "source_media_path": "data/private/path",
            },
            {
                "account": "real_creator_b",
                "post_id": "222",
                "url": "https://example.test/b/222",
                "content_type": "video",
                "created_at": "2026-02-01T00:00:00Z",
                "views": 1000,
                "likes": 100,
                "comments": 10,
                "shares": 50,
                "saves": 80,
                "share_rate": 0.05,
                "save_rate": 0.08,
                "account_views_pct": 0.20,
                "global_views_pct": 0.99,
                "primary_language_code": "es",
                "audience_segment": "college_student",
                "content_angle": "exam_prep",
                "value_type": "educational_reference",
                "hook_technique": "question",
                "video_format": "tool_demo",
                "dominant_visual_type": "app_screenshot",
                "product_family": "single_product",
                "product_placement_style": "soft_reveal",
                "cta_type": "try_product",
                "duration_seconds": 18.0,
                "hook_text": "¿Tienes examen?",
                "creative_formula": "hook -> demo -> cta",
                "analysis_json": "SECRET RAW ANALYSIS 2",
                "source_media_path": "data/private/video",
            },
        ]
    )


def test_export_showcase_is_public_safe_by_default(tmp_path: Path) -> None:
    manifest = export_showcase(sample_master(), tmp_path)
    assert manifest["public_safe_defaults"] is True

    posts = json.loads(
        (tmp_path / "posts.json").read_text(encoding="utf-8")
    )
    assert len(posts) == 2
    assert posts[0]["account_alias"].startswith("Creator ")

    for post in posts:
        assert "account" not in post
        assert "post_id" not in post
        assert "url" not in post
        assert "hook_text" not in post
        assert "creative_formula" not in post
        assert "analysis_json" not in post
        assert "source_media_path" not in post

    serialized = json.dumps(posts)
    assert "real_creator_a" not in serialized
    assert "real_creator_b" not in serialized
    assert "SECRET RAW ANALYSIS" not in serialized


def test_export_showcase_can_opt_in_to_identity_and_text(
    tmp_path: Path,
) -> None:
    export_showcase(
        sample_master(),
        tmp_path,
        include_identities=True,
        include_text=True,
    )

    posts = json.loads(
        (tmp_path / "posts.json").read_text(encoding="utf-8")
    )
    assert posts[0]["account"] == "real_creator_a"
    assert posts[0]["post_id"] == "111"
    assert posts[0]["hook_text"] == "Seven things to learn"
    assert posts[0]["creative_formula"] == "hook -> value -> product"
    assert "analysis_json" not in posts[0]
    assert "source_media_path" not in posts[0]


def test_export_showcase_writes_expected_bundle_and_aggregates(
    tmp_path: Path,
) -> None:
    export_showcase(sample_master(), tmp_path)

    expected = {
        "overview.json",
        "accounts.json",
        "timeline.json",
        "dimensions.json",
        "posts.json",
        "manifest.json",
        "AI_STUDIO_PROMPT.md",
    }
    assert expected.issubset({p.name for p in tmp_path.iterdir()})

    overview = json.loads(
        (tmp_path / "overview.json").read_text(encoding="utf-8")
    )
    assert overview["dataset"]["posts"] == 2
    assert overview["dataset"]["accounts"] == 2
    assert overview["dataset"]["content_types"] == {
        "slideshow": 1,
        "video": 1,
    }
    assert overview["performance"]["total_views"] == 1100
    assert overview["performance"]["median_views"] == 550.0

    dimensions = json.loads(
        (tmp_path / "dimensions.json").read_text(encoding="utf-8")
    )
    assert "hook_technique" in dimensions
    assert {
        item["value"] for item in dimensions["hook_technique"]
    } == {"list_or_number", "question"}
