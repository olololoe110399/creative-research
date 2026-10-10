#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from creative_research.analysis.preview_families_v2 import (
    DEFAULT_BRIDGE_COMBINED,
    DEFAULT_MIN_AI_CONFIDENCE,
    DEFAULT_STRONG_COMBINED,
    _review_table,
    build_family_v2_preview,
)
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_csv, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    posts: str = "data/05_master/posts.parquet",
    analysis: str = "data/05_master/creative_analysis.parquet",
    pairs: str = "data/06_analytics/family_calibration/family_calibration_pairs.parquet",
    out: str = "data/06_analytics/family_v2_preview",
    ai_judgments: str = "data/06_analytics/family_ai/family_ai_judgments.parquet",
    min_ai_confidence: float = DEFAULT_MIN_AI_CONFIDENCE,
    strong_combined: float = DEFAULT_STRONG_COMBINED,
    bridge_combined: float = DEFAULT_BRIDGE_COMBINED,
    review_limit: int = 150,
) -> None:

    posts_path = resolve_path(posts)
    analysis_path = resolve_path(analysis)
    pairs_path = resolve_path(pairs)
    ai_judgments_path = resolve_path(ai_judgments)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    posts_frame = read_table(posts_path)
    analysis_frame = read_table(analysis_path)
    pairs_frame = read_table(pairs_path)
    ai_judgments_frame = read_table(ai_judgments_path) if ai_judgments_path.exists() else None

    result = build_family_v2_preview(
        posts_frame,
        pairs_frame,
        analysis_frame,
        ai_judgments_frame,
        strong_combined=strong_combined,
        bridge_combined=bridge_combined,
        min_ai_confidence=min_ai_confidence,
    )
    families = result["families"]
    members = result["members"]
    report = dict(result["report"])

    families_path = out_dir / "family_v2_preview_families.parquet"
    members_path = out_dir / "family_v2_preview_members.parquet"
    review_path = out_dir / "family_v2_preview_review.csv"
    report_path = out_dir / "family_v2_preview_report.json"

    assert isinstance(families, pd.DataFrame)
    assert isinstance(members, pd.DataFrame)
    write_parquet(families_path, families)
    write_parquet(members_path, members)
    write_csv(
        review_path,
        _review_table(
            families,
            members,
            limit=max(1, review_limit),
        ),
        index=False,
        encoding="utf-8-sig",
    )

    report.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "posts_source": str(posts_path),
            "analysis_source": str(analysis_path),
            "pairs_source": str(pairs_path),
            "ai_judgments_source": (
                str(ai_judgments_path) if ai_judgments_frame is not None else None
            ),
            "outputs": {
                "families": str(families_path),
                "members": str(members_path),
                "review_csv": str(review_path),
                "report": str(report_path),
            },
        }
    )
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
