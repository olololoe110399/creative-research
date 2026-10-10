#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import UTC, datetime

from creative_research.infrastructure.paths import project_root, resolve_path
from creative_research.infrastructure.storage import write_text as atomic_write_text
from creative_research.pipeline.build import (
    PIPELINE_STAGE_NAMES,
    PipelineConfig,
    PipelineExecutionError,
    build_stage_specs,
    execute_pipeline,
    plan_pipeline,
    slice_specs,
)
from creative_research.pipeline.contracts import DEFAULT_WORKSPACE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build/reuse the offline pipeline from creative_master through warehouse, "
            "analytics, knowledge, workspace, quality audit, and outcome audit. "
            "Never invokes scraping or Vision."
        )
    )
    parser.add_argument(
        "--root", default=None, help="Project root; defaults to the active workspace."
    )
    parser.add_argument(
        "--operators",
        default="config/operators.toml",
        help="Verified local operator registry TOML.",
    )
    parser.add_argument("--reviews", default=None, help="Optional local knowledge review TOML.")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--workspace-out", default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--quality-out",
        default=None,
        help="Defaults to quality_report.json inside --workspace-out.",
    )
    parser.add_argument(
        "--profile",
        choices=("full", "evidence-only"),
        default="full",
        help="full (default) preserves all 12 stages; evidence-only ends at timeline.",
    )
    parser.add_argument("--from-stage", choices=PIPELINE_STAGE_NAMES, default=None)
    parser.add_argument("--through-stage", choices=PIPELINE_STAGE_NAMES, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one JSON report on stdout; progress goes to stderr.",
    )
    parser.add_argument(
        "--report", default=None, help="Defaults to pipeline_report.json inside --workspace-out."
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    through_stage = args.through_stage
    if args.profile == "evidence-only":
        if through_stage not in (None, "timeline"):
            parser.error("evidence-only cannot extend past timeline")
        if args.from_stage and PIPELINE_STAGE_NAMES.index(
            args.from_stage
        ) > PIPELINE_STAGE_NAMES.index("timeline"):
            parser.error("evidence-only cannot start after timeline")
        through_stage = "timeline"
    try:
        config = PipelineConfig.from_paths(
            root=resolve_path(args.root) if args.root else project_root(),
            operators=args.operators,
            reviews=args.reviews,
            timezone=args.timezone,
            workspace_out=args.workspace_out,
            quality_out=args.quality_out,
        )
        specs = slice_specs(
            build_stage_specs(config),
            from_stage=args.from_stage,
            through_stage=through_stage,
        )
    except ValueError as exc:
        parser.error(str(exc))
    report_path = (
        resolve_path(args.report, config.root)
        if args.report
        else (
            config.root / "data/06_analytics/evidence_pipeline_report.json"
            if args.profile == "evidence-only"
            else config.workspace_out / "pipeline_report.json"
        )
    )
    plans = plan_pipeline(specs, force=args.force)

    plan_stream = sys.stderr if args.json else sys.stdout
    print("Intelligence build plan:", file=plan_stream)
    for plan in plans:
        print(f"  {plan.name:<12} {plan.action:<7} {plan.reason}", file=plan_stream)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(config.root),
        "timezone": config.timezone,
        "operators": str(config.operators),
        "reviews": str(config.reviews) if config.reviews else None,
        "workspace_out": str(config.workspace_out),
        "quality_out": str(config.quality_out),
        "profile": args.profile,
        "dry_run": args.dry_run,
        "force": args.force,
        "from_stage": args.from_stage,
        "through_stage": through_stage,
    }
    error = None
    try:
        with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
            results = execute_pipeline(specs, plans, dry_run=args.dry_run, root=config.root)
        payload["status"] = (
            "blocked"
            if any(plan.action == "blocked" for plan in plans)
            else "planned"
            if args.dry_run
            else "complete"
        )
    except PipelineExecutionError as exc:
        error = str(exc)
        results = exc.results
        payload["status"] = "failed"
    except FileNotFoundError as exc:
        error = str(exc)
        results = [
            {
                "stage": plan.name,
                "reason": plan.reason,
                "status": "blocked" if plan.action == "blocked" else "not_run",
            }
            for plan in plans
        ]
        payload["status"] = "blocked"
    payload["stages"] = results
    if error is not None:
        payload["error"] = error

    if not args.dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(report_path, json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if error is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
