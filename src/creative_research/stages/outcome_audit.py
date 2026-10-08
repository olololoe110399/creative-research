#!/usr/bin/env python3
"""Validate materialized Research Outcome, without re-scraping or LLM calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from creative_research.outcome_acceptance import audit_outcome
from creative_research.pathing import project_root


REQUIRED = {
    "lab": "lab.json",
    "families": "families.json",
    "strategies": "strategies.json",
    "knowledge": "knowledge.json",
    "evidence": "evidence.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit evidence-to-decision contracts in a materialized Lab."
    )
    parser.add_argument(
        "--workspace", default="data/07_exports/operator-intelligence"
    )
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--strict", action="store_true",
        help="Return nonzero until trusted knowledge is ready for usability testing.",
    )
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser()
    if not workspace.is_absolute():
        workspace = project_root() / workspace
    workspace = workspace.resolve()

    outputs = {}
    for key, filename in REQUIRED.items():
        path = workspace / filename
        if not path.is_file():
            raise SystemExit(f"Missing required Lab artifact: {path}")
        outputs[key] = json.loads(path.read_text(encoding="utf-8"))
    report = audit_outcome(**outputs)
    target = (
        Path(args.out).expanduser()
        if args.out is not None
        else workspace / "outcome_acceptance_report.json"
    )
    if not target.is_absolute():
        target = project_root() / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["status"] == "fail":
        raise SystemExit(1)
    if args.strict and report["status"] != "ready_for_usability_test":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
