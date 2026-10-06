from __future__ import annotations

import pandas as pd

from creative_research.system_map import build_system_map


def test_system_map_uses_full_dataset_and_reports_selection_bias() -> None:
    master = pd.DataFrame(
        [
            {"account": "a", "post_id": "1", "content_type": "slideshow", "created_at": "2026-01-01T00:00:00Z", "views": 1000, "account_views_pct": 0.9, "global_views_pct": 0.9, "save_rate": 0.04, "share_rate": 0.01, "hook_technique": "list", "content_angle": "education", "content_format": "listicle", "product_placement_style": "late_reveal", "cta_type": "try_product", "dominant_visual_type": "notes"},
            {"account": "a", "post_id": "2", "content_type": "slideshow", "created_at": "2026-01-01T01:00:00Z", "views": 500, "account_views_pct": 0.5, "global_views_pct": 0.5, "save_rate": 0.02, "share_rate": 0.01, "hook_technique": "question", "content_angle": "education", "content_format": "listicle", "product_placement_style": "late_reveal", "cta_type": "none", "dominant_visual_type": "study_desk"},
            {"account": "b", "post_id": "3", "content_type": "video", "created_at": "2026-01-02T00:00:00Z", "views": 200, "account_views_pct": 0.8, "global_views_pct": 0.2, "save_rate": 0.01, "share_rate": 0.01, "hook_technique": "direct_address", "content_angle": "demo", "content_format": pd.NA, "product_placement_style": "soft_reveal", "cta_type": "try_product", "dominant_visual_type": "app_screenshot"},
            {"account": "b", "post_id": "4", "content_type": "slideshow", "created_at": "2026-01-03T00:00:00Z", "views": 700, "account_views_pct": 0.95, "global_views_pct": 0.7, "save_rate": 0.03, "share_rate": 0.02, "hook_technique": "how_to", "content_angle": "tutorial", "content_format": "tutorial", "product_placement_style": "none", "cta_type": "save", "dominant_visual_type": "notes"},
        ]
    )
    population = master.loc[master["content_type"] == "slideshow"].copy()
    refs = pd.DataFrame(
        [
            {
                "source_account": "a",
                "hook_technique": "list",
                "content_angle": "education",
                "content_format": "listicle",
                "product_placement_style": "late_reveal",
                "cta_type": "try_product",
                "dominant_visual_type": "notes",
            },
            {
                "source_account": "b",
                "hook_technique": "how_to",
                "content_angle": "tutorial",
                "content_format": "tutorial",
                "product_placement_style": "none",
                "cta_type": "save",
                "dominant_visual_type": "notes",
            },
        ]
    )

    result = build_system_map(
        master,
        population,
        refs,
        strategy="system",
        content_type="slideshow",
    )

    assert result["dataset"]["posts"] == 4
    assert result["dataset"]["accounts"] == 2
    assert result["reference_population"]["posts"] == 3
    assert result["selection"]["account_coverage"] == 1.0
    assert result["selection"]["max_account_share"] == 0.5
    assert len(result["accounts"]) == 2
    assert result["accounts"][0]["active_days"] >= 1
    assert "hook_technique" in result["dimensions"]
