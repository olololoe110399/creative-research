from __future__ import annotations

import runpy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

PIPELINE_STAGE_NAMES = (
    "warehouse",
    "performance",
    "cadence",
    "families",
    "propagation",
    "timeline",
    "patterns",
    "strategies",
    "knowledge",
    "workspace",
    "audit",
    "outcome",
)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    root: Path
    operators: Path
    reviews: Path | None
    timezone: str
    workspace_out: Path
    quality_out: Path


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    module: str
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    args: tuple[str, ...]
    report_expectations: tuple[tuple[Path, str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class StagePlan:
    name: str
    action: str
    reason: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


def _p(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _existing_inputs(paths: Iterable[Path]) -> tuple[Path, ...]:
    return tuple(path for path in paths if path.exists())


def build_stage_specs(config: PipelineConfig) -> tuple[StageSpec, ...]:
    root = config.root.resolve()
    master = _p(root, "data/05_master/creative_master.parquet")
    master_dir = _p(root, "data/05_master")
    analytics = _p(root, "data/06_analytics")
    knowledge = _p(root, "data/07_knowledge")
    workspace = config.workspace_out.resolve()

    warehouse_outputs = tuple(
        master_dir / name
        for name in (
            "operators.parquet",
            "accounts.parquet",
            "posts.parquet",
            "creative_analysis.parquet",
            "creative_sequence.parquet",
            "warehouse_report.json",
        )
    )
    performance_outputs = tuple(
        analytics / name
        for name in (
            "post_performance.parquet",
            "account_performance_baselines.parquet",
            "operator_performance_baselines.parquet",
            "performance_report.json",
        )
    )
    cadence_outputs = tuple(
        analytics / name
        for name in (
            "posting_cadence.parquet",
            "account_activity_daily.parquet",
            "operator_activity_daily.parquet",
            "account_cadence_summary.parquet",
            "operator_cadence_summary.parquet",
            "cadence_report.json",
        )
    )
    family_outputs = tuple(
        analytics / name
        for name in (
            "creative_families.parquet",
            "creative_family_members.parquet",
            "creative_families_report.json",
        )
    )
    propagation_outputs = tuple(
        analytics / name
        for name in (
            "family_account_entries.parquet",
            "cross_account_propagation.parquet",
            "account_propagation_edges.parquet",
            "account_sequence_edges.parquet",
            "account_role_evidence.parquet",
            "propagation_report.json",
        )
    )
    timeline_outputs = tuple(
        analytics / name
        for name in (
            "strategy_windows.parquet",
            "strategy_window_members.parquet",
            "strategy_change_points.parquet",
            "strategy_timeline_report.json",
        )
    )
    pattern_outputs = tuple(
        analytics / name
        for name in (
            "patterns.parquet",
            "pattern_evidence_links.parquet",
            "patterns_report.json",
        )
    )
    strategy_outputs = tuple(
        analytics / name
        for name in (
            "strategy_hypotheses.parquet",
            "account_strategy_hypotheses.parquet",
            "operator_strategy_hypotheses.parquet",
            "strategy_pattern_links.parquet",
            "strategy_evidence_links.parquet",
            "strategy_hypotheses_report.json",
        )
    )

    knowledge_names = (
        "strategies",
        "rules",
        "lessons",
        "templates",
        "playbooks",
        "knowledge_catalog",
        "knowledge_source_links",
        "knowledge_evidence_links",
    )
    knowledge_outputs = tuple(
        knowledge / f"{name}.{suffix}"
        for name in knowledge_names
        for suffix in ("parquet", "jsonl")
    ) + (knowledge / "knowledge_report.json",)

    workspace_outputs = tuple(
        workspace / name
        for name in (
            "workspace.json",
            "overview.json",
            "accounts.json",
            "timeline.json",
            "families.json",
            "patterns.json",
            "strategies.json",
            "knowledge.json",
            "evidence.json",
            "lab.json",
            "index.html",
            "app.js",
            "product_ui.js",
            "ai_ui.js",
            "research_ui.js",
            "style.css",
            "favicon.svg",
        )
    )

    review_inputs = (config.reviews.resolve(),) if config.reviews is not None else ()
    knowledge_args = [
        "--hypotheses",
        str(analytics / "strategy_hypotheses.parquet"),
        "--strategy-evidence",
        str(analytics / "strategy_evidence_links.parquet"),
        "--families",
        str(analytics / "creative_families.parquet"),
        "--family-members",
        str(analytics / "creative_family_members.parquet"),
        "--out",
        str(knowledge),
    ]
    if config.reviews is not None:
        knowledge_args.extend(["--reviews", str(config.reviews.resolve())])

    workspace_args = [
        "--operators",
        str(master_dir / "operators.parquet"),
        "--accounts",
        str(master_dir / "accounts.parquet"),
        "--posts",
        str(master_dir / "posts.parquet"),
        "--creative-analysis",
        str(master_dir / "creative_analysis.parquet"),
        "--creative-sequence",
        str(master_dir / "creative_sequence.parquet"),
        "--performance",
        str(analytics / "post_performance.parquet"),
        "--account-baselines",
        str(analytics / "account_performance_baselines.parquet"),
        "--account-cadence",
        str(analytics / "account_cadence_summary.parquet"),
        "--role-evidence",
        str(analytics / "account_role_evidence.parquet"),
        "--strategy-windows",
        str(analytics / "strategy_windows.parquet"),
        "--strategy-changes",
        str(analytics / "strategy_change_points.parquet"),
        "--families",
        str(analytics / "creative_families.parquet"),
        "--family-members",
        str(analytics / "creative_family_members.parquet"),
        "--propagation",
        str(analytics / "cross_account_propagation.parquet"),
        "--patterns",
        str(analytics / "patterns.parquet"),
        "--pattern-evidence-links",
        str(analytics / "pattern_evidence_links.parquet"),
        "--strategies",
        str(analytics / "strategy_hypotheses.parquet"),
        "--strategy-pattern-links",
        str(analytics / "strategy_pattern_links.parquet"),
        "--strategy-evidence-links",
        str(analytics / "strategy_evidence_links.parquet"),
        "--knowledge",
        str(knowledge / "knowledge_catalog.parquet"),
        "--knowledge-source-links",
        str(knowledge / "knowledge_source_links.parquet"),
        "--knowledge-evidence-links",
        str(knowledge / "knowledge_evidence_links.parquet"),
        "--out",
        str(workspace),
    ]

    audit_inputs = (
        *warehouse_outputs[:-1],
        *performance_outputs[:-1],
        *cadence_outputs[:-1],
        *family_outputs[:-1],
        *propagation_outputs[:-1],
        *timeline_outputs[:-1],
        *pattern_outputs[:-1],
        *strategy_outputs[:-1],
        knowledge / "knowledge_catalog.parquet",
        knowledge / "knowledge_source_links.parquet",
        knowledge / "knowledge_evidence_links.parquet",
        workspace / "workspace.json",
    )

    return (
        StageSpec(
            name="warehouse",
            module="creative_research.stages.build_warehouse",
            inputs=(master, config.operators.resolve()),
            outputs=warehouse_outputs,
            args=(
                str(master),
                "--operators",
                str(config.operators.resolve()),
                "--out",
                str(master_dir),
            ),
            report_expectations=(
                (
                    master_dir / "warehouse_report.json",
                    "operator_registry",
                    str(config.operators.resolve()),
                ),
            ),
        ),
        StageSpec(
            name="performance",
            module="creative_research.stages.analyze_performance",
            inputs=(master_dir / "posts.parquet",),
            outputs=performance_outputs,
            args=(
                str(master_dir / "posts.parquet"),
                "--out",
                str(analytics),
            ),
        ),
        StageSpec(
            name="cadence",
            module="creative_research.stages.analyze_cadence",
            inputs=(master_dir / "posts.parquet",),
            outputs=cadence_outputs,
            args=(
                str(master_dir / "posts.parquet"),
                "--out",
                str(analytics),
                "--timezone",
                config.timezone,
            ),
            report_expectations=(
                (
                    analytics / "cadence_report.json",
                    "timezone",
                    config.timezone,
                ),
            ),
        ),
        StageSpec(
            name="families",
            module="creative_research.stages.build_families",
            inputs=(
                master_dir / "posts.parquet",
                master_dir / "creative_analysis.parquet",
                master_dir / "creative_sequence.parquet",
                analytics / "post_performance.parquet",
                *_existing_inputs(
                    (
                        analytics
                        / "family_ai"
                        / "family_ai_judgments.parquet",
                    )
                ),
            ),
            outputs=family_outputs,
            args=(
                "--posts",
                str(master_dir / "posts.parquet"),
                "--analysis",
                str(master_dir / "creative_analysis.parquet"),
                "--sequence",
                str(master_dir / "creative_sequence.parquet"),
                "--performance",
                str(analytics / "post_performance.parquet"),
                "--ai-judgments",
                str(
                    analytics
                    / "family_ai"
                    / "family_ai_judgments.parquet"
                ),
                "--family-model",
                "v2",
                "--out",
                str(analytics),
            ),
            report_expectations=(
                (
                    analytics / "creative_families_report.json",
                    "family_schema_version",
                    "creative-family-v2",
                ),
            ),
        ),
        StageSpec(
            name="propagation",
            module="creative_research.stages.analyze_propagation",
            inputs=(
                analytics / "creative_family_members.parquet",
                master_dir / "creative_analysis.parquet",
                analytics / "post_performance.parquet",
            ),
            outputs=propagation_outputs,
            args=(
                "--members",
                str(analytics / "creative_family_members.parquet"),
                "--analysis",
                str(master_dir / "creative_analysis.parquet"),
                "--performance",
                str(analytics / "post_performance.parquet"),
                "--out",
                str(analytics),
            ),
        ),
        StageSpec(
            name="timeline",
            module="creative_research.stages.analyze_timeline",
            inputs=(
                master_dir / "posts.parquet",
                master_dir / "creative_analysis.parquet",
                analytics / "post_performance.parquet",
                analytics / "posting_cadence.parquet",
                analytics / "creative_family_members.parquet",
                analytics / "family_account_entries.parquet",
            ),
            outputs=timeline_outputs,
            args=(
                "--posts",
                str(master_dir / "posts.parquet"),
                "--analysis",
                str(master_dir / "creative_analysis.parquet"),
                "--performance",
                str(analytics / "post_performance.parquet"),
                "--cadence",
                str(analytics / "posting_cadence.parquet"),
                "--family-members",
                str(analytics / "creative_family_members.parquet"),
                "--family-entries",
                str(analytics / "family_account_entries.parquet"),
                "--timezone",
                config.timezone,
                "--out",
                str(analytics),
            ),
            report_expectations=(
                (
                    analytics / "strategy_timeline_report.json",
                    "timezone",
                    config.timezone,
                ),
            ),
        ),
        StageSpec(
            name="patterns",
            module="creative_research.stages.discover_patterns",
            inputs=(
                master_dir / "creative_analysis.parquet",
                analytics / "post_performance.parquet",
                analytics / "posting_cadence.parquet",
                analytics / "creative_families.parquet",
                analytics / "creative_family_members.parquet",
                analytics / "cross_account_propagation.parquet",
                analytics / "account_role_evidence.parquet",
                analytics / "strategy_change_points.parquet",
                analytics / "strategy_window_members.parquet",
            ),
            outputs=pattern_outputs,
            args=(
                "--analysis",
                str(master_dir / "creative_analysis.parquet"),
                "--performance",
                str(analytics / "post_performance.parquet"),
                "--cadence",
                str(analytics / "posting_cadence.parquet"),
                "--families",
                str(analytics / "creative_families.parquet"),
                "--family-members",
                str(analytics / "creative_family_members.parquet"),
                "--propagation",
                str(analytics / "cross_account_propagation.parquet"),
                "--role-evidence",
                str(analytics / "account_role_evidence.parquet"),
                "--strategy-changes",
                str(analytics / "strategy_change_points.parquet"),
                "--strategy-members",
                str(analytics / "strategy_window_members.parquet"),
                "--out",
                str(analytics),
            ),
        ),
        StageSpec(
            name="strategies",
            module="creative_research.stages.infer_strategies",
            inputs=(
                analytics / "patterns.parquet",
                analytics / "pattern_evidence_links.parquet",
            ),
            outputs=strategy_outputs,
            args=(
                "--patterns",
                str(analytics / "patterns.parquet"),
                "--pattern-evidence",
                str(analytics / "pattern_evidence_links.parquet"),
                "--out",
                str(analytics),
            ),
        ),
        StageSpec(
            name="knowledge",
            module="creative_research.stages.promote_knowledge",
            inputs=(
                analytics / "strategy_hypotheses.parquet",
                analytics / "strategy_evidence_links.parquet",
                analytics / "creative_families.parquet",
                analytics / "creative_family_members.parquet",
                *review_inputs,
            ),
            outputs=knowledge_outputs,
            args=tuple(knowledge_args),
            report_expectations=(
                (
                    knowledge / "knowledge_report.json",
                    "reviews_source",
                    str(config.reviews.resolve()) if config.reviews is not None else None,
                ),
                (
                    knowledge / "knowledge_report.json",
                    "knowledge_schema_version",
                    "operator-knowledge-v2",
                ),
            ),
        ),
        StageSpec(
            name="workspace",
            module="creative_research.stages.build_intelligence_workspace",
            inputs=(
                master_dir / "operators.parquet",
                master_dir / "accounts.parquet",
                master_dir / "posts.parquet",
                master_dir / "creative_analysis.parquet",
                master_dir / "creative_sequence.parquet",
                analytics / "post_performance.parquet",
                analytics / "account_performance_baselines.parquet",
                analytics / "account_cadence_summary.parquet",
                analytics / "account_role_evidence.parquet",
                analytics / "strategy_windows.parquet",
                analytics / "strategy_change_points.parquet",
                analytics / "creative_families.parquet",
                analytics / "creative_family_members.parquet",
                analytics / "cross_account_propagation.parquet",
                analytics / "patterns.parquet",
                analytics / "pattern_evidence_links.parquet",
                analytics / "strategy_hypotheses.parquet",
                analytics / "strategy_pattern_links.parquet",
                analytics / "strategy_evidence_links.parquet",
                knowledge / "knowledge_catalog.parquet",
                knowledge / "knowledge_source_links.parquet",
                knowledge / "knowledge_evidence_links.parquet",
            ),
            outputs=workspace_outputs,
            args=tuple(workspace_args),
            report_expectations=(
                (
                    workspace / "workspace.json",
                    "workspace_schema_version",
                    "operator-intelligence-lab-v3",
                ),
            ),
        ),
        StageSpec(
            name="audit",
            module="creative_research.stages.quality_audit",
            inputs=tuple(audit_inputs),
            outputs=(config.quality_out.resolve(),),
            args=tuple(
                [
                    "--root",
                    str(root),
                    "--operators",
                    str(config.operators.resolve()),
                    "--timezone",
                    config.timezone,
                    "--workspace",
                    str(workspace),
                    "--out",
                    str(config.quality_out.resolve()),
                ]
                + (
                    ["--reviews", str(config.reviews.resolve())]
                    if config.reviews is not None
                    else []
                )
            ),
        ),
        StageSpec(
            name="outcome",
            module="creative_research.stages.outcome_audit",
            inputs=tuple(workspace / name for name in (
                "lab.json",
                "families.json",
                "strategies.json",
                "knowledge.json",
                "evidence.json",
            )) + (config.quality_out.resolve(),),
            outputs=(workspace / "outcome_acceptance_report.json",),
            args=(
                "--workspace",
                str(workspace),
                "--out",
                str(workspace / "outcome_acceptance_report.json"),
            ),
        ),
    )


def slice_specs(
    specs: tuple[StageSpec, ...],
    *,
    from_stage: str | None = None,
    through_stage: str | None = None,
) -> tuple[StageSpec, ...]:
    names = [spec.name for spec in specs]
    start = 0
    end = len(specs)
    if from_stage is not None:
        if from_stage not in names:
            raise ValueError(
                f"Unknown from-stage {from_stage!r}; expected one of {names}"
            )
        start = names.index(from_stage)
    if through_stage is not None:
        if through_stage not in names:
            raise ValueError(
                f"Unknown through-stage {through_stage!r}; expected one of {names}"
            )
        end = names.index(through_stage) + 1
    if start >= end:
        raise ValueError("from-stage must not come after through-stage")
    return specs[start:end]


def stage_freshness(spec: StageSpec) -> tuple[str, str]:
    missing_inputs = [path for path in spec.inputs if not path.exists()]
    if missing_inputs:
        rendered = ", ".join(str(path) for path in missing_inputs[:4])
        suffix = " ..." if len(missing_inputs) > 4 else ""
        return "blocked", f"missing inputs: {rendered}{suffix}"

    missing_outputs = [path for path in spec.outputs if not path.exists()]
    if missing_outputs:
        rendered = ", ".join(str(path) for path in missing_outputs[:4])
        suffix = " ..." if len(missing_outputs) > 4 else ""
        return "run", f"missing outputs: {rendered}{suffix}"

    for report_path, key, expected in spec.report_expectations:
        try:
            import json
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "run", f"cannot verify stage parameters from {report_path}"
        if payload.get(key) != expected:
            return (
                "run",
                f"stage parameter {key} changed from {payload.get(key)!r} to {expected!r}",
            )

    existing_inputs = _existing_inputs(spec.inputs)
    newest_input = max(path.stat().st_mtime_ns for path in existing_inputs)
    oldest_output = min(path.stat().st_mtime_ns for path in spec.outputs)
    if oldest_output < newest_input:
        return "run", "at least one input is newer than the oldest output"
    return "skip", "outputs exist and are newer than all inputs"


def plan_pipeline(
    specs: tuple[StageSpec, ...],
    *,
    force: bool = False,
) -> tuple[StagePlan, ...]:
    plans: list[StagePlan] = []
    planned_outputs: set[Path] = set()
    for spec in specs:
        action, reason = stage_freshness(spec)
        missing_inputs = {
            path for path in spec.inputs if not path.exists()
        }
        dependency_will_change = any(
            path in planned_outputs for path in spec.inputs
        )
        if (
            action == "blocked"
            and missing_inputs
            and missing_inputs.issubset(planned_outputs)
        ):
            action, reason = "run", "inputs will be produced by planned dependencies"
        if force and action != "blocked":
            action, reason = "run", "forced by --force"
        elif dependency_will_change and action != "blocked":
            action, reason = "run", "an input dependency will be rebuilt"
        if action == "run":
            planned_outputs.update(spec.outputs)
        plans.append(
            StagePlan(
                name=spec.name,
                action=action,
                reason=reason,
                inputs=tuple(str(path) for path in spec.inputs),
                outputs=tuple(str(path) for path in spec.outputs),
            )
        )
    return tuple(plans)


def _run_module(module: str, args: tuple[str, ...]) -> None:
    old_argv = sys.argv[:]
    try:
        sys.argv = [module, *args]
        try:
            runpy.run_module(module, run_name="__main__")
        except SystemExit as exc:
            code = exc.code
            if code not in (None, 0):
                raise RuntimeError(
                    f"{module} exited with status {code}"
                ) from exc
    finally:
        sys.argv = old_argv


def execute_pipeline(
    specs: tuple[StageSpec, ...],
    plans: tuple[StagePlan, ...],
    *,
    dry_run: bool = False,
    runner: Callable[[str, tuple[str, ...]], None] = _run_module,
) -> list[dict[str, str]]:
    plan_by_name = {plan.name: plan for plan in plans}
    results: list[dict[str, str]] = []
    for spec in specs:
        plan = plan_by_name[spec.name]
        if plan.action == "blocked":
            raise FileNotFoundError(
                f"Stage {spec.name} is blocked: {plan.reason}"
            )
        if plan.action == "skip":
            results.append(
                {
                    "stage": spec.name,
                    "status": "reused",
                    "reason": plan.reason,
                }
            )
            continue
        if dry_run:
            results.append(
                {
                    "stage": spec.name,
                    "status": "would_run",
                    "reason": plan.reason,
                }
            )
            continue
        runner(spec.module, spec.args)
        missing_outputs = [path for path in spec.outputs if not path.exists()]
        if missing_outputs:
            raise RuntimeError(
                f"Stage {spec.name} completed without required outputs: "
                + ", ".join(str(path) for path in missing_outputs)
            )
        results.append(
            {
                "stage": spec.name,
                "status": "rebuilt",
                "reason": plan.reason,
            }
        )
    return results
