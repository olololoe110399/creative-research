"""Small synthetic corpus for offline onboarding and full-pipeline regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.constants import MASTER_REQUIRED_COLUMNS, MASTER_SCHEMA_VERSION
from creative_research.infrastructure.storage import write_parquet, write_text


def seed_demo(root: Path) -> None:
    """Create fake, deterministic evidence; caller must supply an empty directory."""
    operators = root / "config/operators.toml"
    operators.parent.mkdir(parents=True)
    write_text(
        operators,
        '[[operators]]\noperator_id = "OP1"\nname = "Synthetic demo - not real research"\n'
        'verified = true\nverification_method = "manual"\n'
        '[[operators.accounts]]\nusername = "alpha"\n'
        '[[operators.accounts]]\nusername = "beta"\n',
    )
    rows = []
    for index in range(8):
        account = "alpha" if index % 2 == 0 else "beta"
        row = dict.fromkeys(sorted(MASTER_REQUIRED_COLUMNS))
        row.update(
            master_schema_version=MASTER_SCHEMA_VERSION,
            account=account,
            post_id=str(index),
            content_type="slideshow",
            created_at=f"2026-01-{index + 1:02d}T12:00:00Z",
            url=f"https://example.test/synthetic/{account}/{index}",
            views=1000 + index * 100,
            likes=100,
            comments=10,
            shares=20,
            saves=40,
            source_media_path=f"data/02_media/tiktok/{account}/{index}",
            primary_language_code="en",
            audience_segment="college_student",
            niche="student study",
            topic="study mistakes and active recall",
            content_angle="study_method",
            hook_technique="list_or_number",
            hook_text="3 study mistakes students should stop making",
            hook_replicable_formula="N study mistakes students should stop making",
            creative_formula="mistakes hook -> better method -> proof -> CTA",
            content_format="listicle",
            value_type="how_to",
            product_family="none",
            product_placement_style="none",
            cta_type="save",
            dominant_visual_type="notes_or_document",
            analysis_json=json.dumps(
                {
                    "slides": [
                        {
                            "slide_index": 1,
                            "role": "hook",
                            "primary_overlay_text": "Study mistakes",
                        },
                        {
                            "slide_index": 2,
                            "role": "body",
                            "primary_overlay_text": "Use active recall",
                        },
                    ]
                }
            ),
        )
        rows.append(row)
    master = root / "data/05_master/creative_master.parquet"
    master.parent.mkdir(parents=True)
    write_parquet(master, pd.DataFrame(rows))
