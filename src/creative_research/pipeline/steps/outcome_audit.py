#!/usr/bin/env python3
"""Validate materialized Research Outcome, without re-scraping or LLM calls."""

from __future__ import annotations

import json

from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import write_text as atomic_write_text
from creative_research.operating.acceptance import audit_outcome
from creative_research.pipeline.contracts import DEFAULT_WORKSPACE, OUTCOME_INPUTS


def run(
    *,
    workspace: str = DEFAULT_WORKSPACE,
    out: str | None = None,
    strict: bool = False,
) -> None:
    workspace_dir = resolve_path(workspace)

    outputs = {}
    for key, filename in OUTCOME_INPUTS.items():
        path = workspace_dir / filename
        if not path.is_file():
            raise SystemExit(f"Missing required Lab artifact: {path}")
        outputs[key] = json.loads(path.read_text(encoding="utf-8"))
    report = audit_outcome(**outputs)
    target = (
        resolve_path(out) if out is not None else workspace_dir / "outcome_acceptance_report.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["status"] == "fail":
        raise SystemExit(1)
    if strict and report["status"] != "ready_for_usability_test":
        raise SystemExit(2)
