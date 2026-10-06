from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.reference_workspace import (
    build_reference_detail,
    validate_reference_workspace,
    write_reference_workspace,
)


def analysis_json() -> str:
    return json.dumps(
        {
            "hook": {
                "text": "5 study mistakes",
                "slide_index": 1,
                "technique": "list_or_number",
                "psychological_trigger": "curiosity",
                "replicable_formula": "N mistakes + audience",
            },
            "slides": [
                {"slide_index": 1, "role": "hook", "primary_overlay_text": "5 study mistakes", "text_regions": [], "visual_type": "study_desk", "visual_description": "desk", "product_visible": False, "product_family_visible": "none", "confidence": 0.98},
                {"slide_index": 2, "role": "value", "primary_overlay_text": "Active recall", "text_regions": [], "visual_type": "notes_or_document", "visual_description": "notes", "product_visible": False, "product_family_visible": "none", "confidence": 0.95},
                {"slide_index": 3, "role": "cta", "primary_overlay_text": "Try the app", "text_regions": [], "visual_type": "app_screenshot", "visual_description": "app", "product_visible": True, "product_family_visible": "single_product", "confidence": 0.97},
            ],
            "narrative_structure": ["hook", "value", "cta"],
            "content_format": "listicle",
            "visual_style": {"dominant_visual_type": "notes_or_document", "aesthetic": "study aesthetic", "image_realism": "appears_real_photo", "pinterest_like_aesthetic": "yes", "text_overlay_style": "large overlay", "visual_consistency_across_slides": "high"},
            "product": {"has_visible_product": True, "product_family": "single_product", "visible_product_name": "Study App", "first_appearance_slide": 3, "placement_style": "late_reveal", "evidence": ["slide 3 screenshot"]},
            "cta": {"has_visible_cta": True, "cta_type": "try_product", "text": "Try the app", "slide_index": 3, "evidence": ["slide 3"]},
            "proof_or_credibility": [],
            "attention_mechanisms_used": ["numbered hook"],
            "creative_formula": "list hook -> value -> product CTA",
            "overall_confidence": 0.96,
            "uncertainty_notes": [],
        }
    )


def ref_row() -> dict[str, object]:
    return {
        "reference_schema_version": "creative-reference-pack-v2", "reference_id": "REF-0001", "selection_strategy": "top", "rank_mode": "relative", "rank_position": 1, "rank_score": 0.97, "source_platform": "tiktok", "source_account": "creator", "source_post_id": "123", "source_url": "https://example.test/123", "created_at": "2026-01-01T00:00:00Z", "views": 10000, "save_rate": 0.04, "share_rate": 0.01, "account_views_pct": 0.97, "global_views_pct": 0.90, "primary_language_code": "en", "audience_segment": "student", "niche": "study", "topic": "active recall", "content_angle": "education", "value_type": "how_to", "hook_text": "5 study mistakes", "hook_technique": "list_or_number", "content_format": "listicle", "slide_count": 3, "product_family": "single_product", "product_placement_style": "late_reveal", "product_position": 3, "cta_type": "try_product", "cta_position": 3, "dominant_visual_type": "notes_or_document", "visual_aesthetic": "study aesthetic", "creative_formula": "list hook -> value -> product CTA",
    }


def source_row() -> dict[str, object]:
    return {"account": "creator", "post_id": "123", "url": "https://example.test/123", "content_type": "slideshow", "analysis_json": analysis_json()}


def test_detail_exposes_existing_slide_level_vision_without_raw_analysis(tmp_path: Path) -> None:
    detail = build_reference_detail(ref_row(), source_row(), out_dir=tmp_path, media_mode="none")
    assert detail["sequence"][0]["role"] == "hook"
    assert detail["sequence"][1]["primary_text"] == "Active recall"
    assert detail["product"]["first_position"] == 3
    assert detail["blueprint"]["sequence_roles"] == ["hook", "value", "cta"]
    assert "analysis_json" not in json.dumps(detail)


def test_workspace_writes_details_groups_and_static_files(tmp_path: Path) -> None:
    refs = pd.DataFrame([ref_row()])
    sources = pd.DataFrame([source_row()])
    report = write_reference_workspace(refs, sources, out_dir=tmp_path, media_mode="none")
    assert report["details"] == 1
    assert (tmp_path / "details/REF-0001.json").is_file()
    assert (tmp_path / "workspace.json").is_file()
    assert (tmp_path / "candidate_groups.json").is_file()
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert validate_reference_workspace(tmp_path) == []
