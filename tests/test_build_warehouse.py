from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from creative_research.constants import MASTER_REQUIRED_COLUMNS, MASTER_SCHEMA_VERSION
from creative_research.operator_registry import load_operator_registry
from creative_research.reference_workspace import population_item_id
from creative_research.stages.build_warehouse import build_warehouse


def _master_row(**overrides):
    row = {column: None for column in MASTER_REQUIRED_COLUMNS}
    row.update(
        {
            "master_schema_version": MASTER_SCHEMA_VERSION,
            "account": "creator_a",
            "post_id": "1",
            "content_type": "slideshow",
            "created_at": "2026-01-01T00:00:00Z",
            "views": 100,
            "likes": 10,
            "comments": 2,
            "shares": 1,
            "saves": 3,
            "source_media_path": "data/02_media/tiktok/creator_a/1",
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


def _registry(tmp_path: Path):
    path = tmp_path / "operators.toml"
    path.write_text(
        """
[[operators]]
operator_id = "OP-001"
name = "Verified operator"
verified = true
verification_method = "manual"

[[operators.accounts]]
username = "creator_a"

[[operators.accounts]]
username = "creator_b"
""".strip(),
        encoding="utf-8",
    )
    return load_operator_registry(path)


def test_build_warehouse_backfills_existing_slide_and_video_analysis(tmp_path: Path) -> None:
    slide_analysis = {
        "slides": [
            {
                "slide_index": 1,
                "role": "hook",
                "primary_overlay_text": "Stop doing this",
                "text_regions": [],
                "visual_type": "study_desk_photo",
                "visual_description": "desk",
                "product_visible": False,
                "product_family_visible": "none",
                "confidence": 0.97,
            }
        ]
    }
    video_analysis = {
        "timeline": [
            {
                "start_second": 0.0,
                "end_second": 2.0,
                "role": "hook",
                "visual_type": "talking_head",
                "visual_description": "creator speaking",
                "spoken_summary": "Do this instead",
                "overlay_text": None,
                "product_visible": False,
                "product_family_visible": "none",
            }
        ]
    }
    master = pd.DataFrame(
        [
            _master_row(analysis_json=json.dumps(slide_analysis)),
            _master_row(
                account="creator_b",
                post_id="2",
                content_type="video",
                created_at="2026-01-02T00:00:00Z",
                source_media_path="data/03_video_media/creator_b/2",
                analysis_json=json.dumps(video_analysis),
            ),
        ]
    )

    tables = build_warehouse(master, _registry(tmp_path))

    assert len(tables["operators"]) == 1
    assert len(tables["accounts"]) == 2
    assert len(tables["posts"]) == 2
    assert len(tables["creative_analysis"]) == 2
    assert len(tables["creative_sequence"]) == 2

    posts = tables["posts"].set_index("post_id")
    assert posts.loc["1", "operator_id"] == "OP-001"
    assert posts.loc["1", "post_uid"] == population_item_id("creator_a", "1")

    sequence = tables["creative_sequence"].set_index(["post_id", "position"])
    assert sequence.loc[("1", 1), "role"] == "hook"
    assert sequence.loc[("1", 1), "primary_text"] == "Stop doing this"
    assert sequence.loc[("2", 1), "sequence_type"] == "timeline_beat"
    assert sequence.loc[("2", 1), "primary_text"] == "Do this instead"


def test_build_warehouse_requires_registry_coverage_by_default(tmp_path: Path) -> None:
    master = pd.DataFrame([_master_row(account="unknown")])
    with pytest.raises(ValueError, match="Unmapped accounts"):
        build_warehouse(master, _registry(tmp_path))
