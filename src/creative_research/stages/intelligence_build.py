#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from creative_research.intelligence_pipeline import (
    PIPELINE_STAGE_NAMES,
    PipelineConfig,
    build_stage_specs,
    execute_pipeline,
    plan_pipeline,
    slice_specs,
)
from creative_research.pathing import project_root


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the deterministic operator-intelligence pipeline from creative_master "
            "through warehouse, analytics, knowledge, workspace, and quality audit. "
            "Fresh outputs are reused automatically."
        )
    )
    parser.add_argument(
        "--operators",
        default="config/operators.toml",
        help="Verified local operator registry TOML.",
    )
    parser.add_argument(
        "--reviews",
        default=None,
        help="Optional local knowledge review TOML.",
    )
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument(
        "--workspace-out",
        default="data/07_exports/operator-intelligence",
    )
    parser.add_argument(
        "--quality-out",
        default="data/07_exports/operator-intelligence/quality_report.json",
    )
    parser.add_argument(
        "--from-stage",
        choices=PIPELINE_STAGE_NAMES,
        default=None,
    )
    parser.add_argument(
        "--through-stage",
        choices=PIPELINE_STAGE_NAMES,
        default=None,
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--report",
        default="data/07_exports/operator-intelligence/pipeline_report.json",
    )
    args = parser.parse_args()

    root = project_root().resolve()
    operators = _resolve(root, args.operators)
    reviews = _resolve(root, args.reviews) if args.reviews else None
    workspace_out = _resolve(root, args.workspace_out)
    quality_out = _resolve(root, args.quality_out)
    report_path = _resolve(root, args.report)

    master = root / "data/05_master/creative_master.parquet"
    if not master.exists():
        raise SystemExit(
            f"Missing canonical creative_master: {master}\n"
            "This orchestrator intentionally starts after Vision/build-master so it never "
            "re-scrapes or reruns expensive interpretation."
        )
    if not operators.exists():
        raise SystemExit(
            f"Missing operator registry: {operators}\n"
            "Create it from config/operators.example.toml before building intelligence."
        )
    if reviews is not None and not reviews.exists():
        raise SystemExit(f"Knowledge reviews file does not exist: {reviews}")

    config = PipelineConfig(
        root=root,
        operators=operators,
        reviews=reviews,
        timezone=args.timezone,
        workspace_out=workspace_out,
        quality_out=quality_out,
    )
    specs = slice_specs(
        build_stage_specs(config),
        from_stage=args.from_stage,
        through_stage=args.through_stage,
    )
    plans = plan_pipeline(specs, force=args.force)

    print("Intelligence build plan:")
    for plan in plans:
        print(f"  {plan.name:<12} {plan.action:<7} {plan.reason}")

    results = execute_pipeline(
        specs,
        plans,
        dry_run=args.dry_run,
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "timezone": args.timezone,
        "operators": str(operators),
        "reviews": str(reviews) if reviews else None,
        "workspace_out": str(workspace_out),
        "quality_out": str(quality_out),
        "dry_run": args.dry_run,
        "force": args.force,
        "from_stage": args.from_stage,
        "through_stage": args.through_stage,
        "stages": results,
    }

    if not args.dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
