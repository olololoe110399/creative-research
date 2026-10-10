#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.infrastructure.paths import project_root, resolve_path
from creative_research.infrastructure.storage import read_table
from creative_research.pipeline.contracts import DEFAULT_WORKSPACE, WORKSPACE_INPUTS
from creative_research.workspaces.lab import write_intelligence_workspace


def _read_optional(path: Path) -> pd.DataFrame | None:
    return read_table(path) if path.exists() else None


def run(
    *,
    out: str = DEFAULT_WORKSPACE,
    raw_root: str | None = None,
    **inputs: str,
) -> None:
    unknown = inputs.keys() - WORKSPACE_INPUTS.keys()
    if unknown:
        raise ValueError("Unknown workspace inputs: " + ", ".join(sorted(unknown)))

    frames: dict[str, pd.DataFrame | None] = {}
    sources: dict[str, str] = {}
    for name in WORKSPACE_INPUTS:
        raw = inputs.get(name, WORKSPACE_INPUTS[name])
        path = resolve_path(raw)
        sources[name] = str(path)
        frames[name] = _read_optional(path)

    required = ("operators", "accounts", "posts", "creative_analysis")
    missing = [name for name in required if frames[name] is None]
    if missing:
        raise SystemExit("Missing required intelligence inputs: " + ", ".join(missing))

    report = write_intelligence_workspace(
        out_dir=resolve_path(out),
        sources=sources,
        raw_root=(
            resolve_path(raw_root) if raw_root is not None else project_root() / "data/00_raw/apify"
        ),
        **frames,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
