"""Portable dataset handoff contract, independent of acquisition providers."""

from __future__ import annotations

DATASET_EXPORT_SCHEMA_VERSION = "creative-dataset-export-v1"
PIPELINE_STATE_SCHEMA_VERSION = "creative-capture-run-v1"
PIPELINE_STAGES = ("scrape", "download", "export", "validate")
DATASET_FILES = frozenset(
    {
        "posts.jsonl",
        "posts.csv",
        "assets.jsonl",
        "missing_assets.jsonl",
        "manifest.json",
        "README.md",
    }
)
