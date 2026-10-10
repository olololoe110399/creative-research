"""Command-line adapter for build master workflow."""

from __future__ import annotations

import argparse

import creative_research.pipeline.steps.build_master as service


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Merge slideshow + video Vision outputs into creative_master."
    )
    ap.add_argument("--slides", required=True, help="creative_study_v2.parquet/csv/jsonl")
    ap.add_argument("--videos", required=True, help="creative_video_study.parquet/csv/jsonl")
    ap.add_argument("--out", default="data/05_master")
    return ap


def main() -> None:
    args = build_parser().parse_args()
    service.run(**vars(args))


if __name__ == "__main__":
    main()
