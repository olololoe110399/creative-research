#!/usr/bin/env python3
"""Command adapter for deterministic analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from creative_research.analysis.calibrate_families import (
    DEFAULT_MAX_PAIRS,
    DEFAULT_MIN_COMBINED,
    DEFAULT_MIN_STRUCTURE,
    DEFAULT_PROGRESS_EVERY,
    _review_sample,
    calibrate_family_pairs,
)
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import read_table, write_csv, write_parquet
from creative_research.infrastructure.storage import write_text as atomic_write_text


def run(
    *,
    posts: str = "data/05_master/posts.parquet",
    analysis: str = "data/05_master/creative_analysis.parquet",
    sequence: str = "data/05_master/creative_sequence.parquet",
    members: str = "data/06_analytics/creative_family_members.parquet",
    out: str = "data/06_analytics/family_calibration",
    min_structure: float = DEFAULT_MIN_STRUCTURE,
    min_combined: float = DEFAULT_MIN_COMBINED,
    max_pairs: int = DEFAULT_MAX_PAIRS,
    review_per_bucket: int = 30,
    progress_every: int = DEFAULT_PROGRESS_EVERY,
) -> None:

    posts_path = resolve_path(posts)
    analysis_path = resolve_path(analysis)
    sequence_path = resolve_path(sequence)
    members_path = resolve_path(members)
    out_dir = resolve_path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    posts_frame = read_table(posts_path)
    analysis_frame = read_table(analysis_path)
    sequence_frame = read_table(sequence_path)
    members_frame = read_table(members_path) if members_path.exists() else None

    def progress(
        processed: int,
        total: int,
        structure_screened: int,
        semantic_scored: int,
        retained: int,
    ) -> None:
        print(
            "Family calibration: "
            f"{processed}/{total} candidate pairs · "
            f"{structure_screened} structure-screened · "
            f"{semantic_scored} semantic-scored · "
            f"{retained} retained",
            flush=True,
        )

    pairs, report = calibrate_family_pairs(
        posts_frame,
        analysis_frame,
        sequence_frame,
        members_frame,
        min_structure=min_structure,
        min_combined=min_combined,
        max_pairs=max_pairs,
        progress_every=max(0, progress_every),
        progress_callback=progress,
    )
    review = _review_sample(
        pairs,
        per_bucket=max(1, review_per_bucket),
    )

    pairs_path = out_dir / "family_calibration_pairs.parquet"
    csv_path = out_dir / "family_calibration_review.csv"
    report_path = out_dir / "family_calibration_report.json"

    write_parquet(pairs_path, pairs)
    write_csv(csv_path, review, index=False, encoding="utf-8-sig")

    report.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "posts_source": str(posts_path),
            "analysis_source": str(analysis_path),
            "sequence_source": str(sequence_path),
            "members_source": (str(members_path) if members_frame is not None else None),
            "outputs": {
                "pairs": str(pairs_path),
                "review_csv": str(csv_path),
                "report": str(report_path),
            },
        }
    )
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
