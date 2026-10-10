from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from creative_research.infrastructure.config import project_context
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.source_graph import implementation_sources
from creative_research.infrastructure.storage import write_json
from creative_research.pipeline.contracts import (
    DEFAULT_WORKSPACE,
    OUTCOME_INPUTS,
    REQUIRED_DATA_FILES,
    STATIC_FILES,
    WORKSPACE_INPUTS,
    WORKSPACE_SCHEMA_VERSION,
)

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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    root: Path
    operators: Path
    reviews: Path | None
    timezone: str
    workspace_out: Path
    quality_out: Path

    def __post_init__(self) -> None:
        root = self.root.expanduser().resolve()
        object.__setattr__(self, "root", root)
        for name in ("operators", "reviews", "workspace_out", "quality_out"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, resolve_path(value, root))
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {self.timezone}") from exc

    @classmethod
    def from_paths(
        cls,
        *,
        root: Path,
        operators: str | Path = "config/operators.toml",
        reviews: str | Path | None = None,
        timezone: str = "UTC",
        workspace_out: str | Path = DEFAULT_WORKSPACE,
        quality_out: str | Path | None = None,
    ) -> PipelineConfig:
        root = root.expanduser().resolve()
        workspace = resolve_path(workspace_out, root)
        return cls(
            root=root,
            operators=Path(operators),
            reviews=Path(reviews) if reviews is not None else None,
            timezone=timezone,
            workspace_out=workspace,
            quality_out=(
                resolve_path(quality_out, root)
                if quality_out is not None
                else workspace / "quality_report.json"
            ),
        )


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    module: str
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    args: tuple[str, ...]
    report_expectations: tuple[tuple[Path, str, object], ...] = ()
    execution_marker: Path | None = None
    parameters: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class StagePlan:
    name: str
    action: str
    reason: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


def _arguments(values: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        token
        for name, value in values.items()
        if value is not None
        for token in ((f"--{name}", str(value)) if name else (str(value),))
    )


def _stage(
    name: str,
    module: str,
    inputs: Mapping[str, Path],
    outputs: tuple[Path, ...],
    *,
    options: Mapping[str, object] | None = None,
    optional_inputs: tuple[str, ...] = (),
    extra_inputs: tuple[Path, ...] = (),
    expectations: tuple[tuple[Path, str, object], ...] = (),
) -> StageSpec:
    """Declare workflow inputs once, deriving execution parameters and dependency edges."""
    package = Path(__file__).parent
    task_module = f"creative_research.pipeline.steps.{module}"
    positional_names = {
        "build_warehouse": "master",
        "analyze_performance": "posts",
        "analyze_cadence": "posts",
    }
    parameters = {
        (flag.replace("-", "_") if flag else positional_names[module]): (
            str(value) if isinstance(value, Path) else value
        )
        for flag, value in {**inputs, **(options or {})}.items()
        if value is not None
    }
    implementation_inputs = (
        *implementation_sources(task_module),
        package / "build.py",
        package / "contracts.py",
    )
    return StageSpec(
        name=name,
        module=task_module,
        inputs=tuple(
            path for flag, path in inputs.items() if flag not in optional_inputs or path.exists()
        )
        + extra_inputs
        + implementation_inputs,
        outputs=outputs,
        args=_arguments(inputs) + _arguments(options or {}),
        report_expectations=expectations,
        execution_marker=outputs[0].parent / ".pipeline" / f"{name}.json",
        parameters=MappingProxyType(parameters),
    )


def build_stage_specs(config: PipelineConfig) -> tuple[StageSpec, ...]:
    root = config.root
    master = resolve_path("data/05_master", root)
    analytics = resolve_path("data/06_analytics", root)
    knowledge = resolve_path("data/07_knowledge", root)
    workspace = config.workspace_out
    ai_judgments = (analytics / "family_ai/family_ai_judgments.parquet").resolve()

    def outputs(directory: Path, *names: str) -> tuple[Path, ...]:
        return tuple(directory / name for name in names)

    specs = [
        _stage(
            "warehouse",
            "build_warehouse",
            {"": master / "creative_master.parquet", "operators": config.operators},
            outputs(
                master,
                "operators.parquet",
                "accounts.parquet",
                "posts.parquet",
                "creative_analysis.parquet",
                "creative_sequence.parquet",
                "warehouse_report.json",
            ),
            options={"out": master},
            expectations=(
                (master / "warehouse_report.json", "operator_registry", str(config.operators)),
            ),
        ),
        _stage(
            "performance",
            "analyze_performance",
            {"": master / "posts.parquet"},
            outputs(
                analytics,
                "post_performance.parquet",
                "account_performance_baselines.parquet",
                "operator_performance_baselines.parquet",
                "performance_report.json",
            ),
            options={"out": analytics},
        ),
        _stage(
            "cadence",
            "analyze_cadence",
            {"": master / "posts.parquet"},
            outputs(
                analytics,
                "posting_cadence.parquet",
                "account_activity_daily.parquet",
                "operator_activity_daily.parquet",
                "account_cadence_summary.parquet",
                "operator_cadence_summary.parquet",
                "cadence_report.json",
            ),
            options={"out": analytics, "timezone": config.timezone},
            expectations=((analytics / "cadence_report.json", "timezone", config.timezone),),
        ),
        _stage(
            "families",
            "build_families",
            {
                "posts": master / "posts.parquet",
                "analysis": master / "creative_analysis.parquet",
                "sequence": master / "creative_sequence.parquet",
                "performance": analytics / "post_performance.parquet",
                "ai-judgments": ai_judgments,
            },
            outputs(
                analytics,
                "creative_families.parquet",
                "creative_family_members.parquet",
                "creative_families_report.json",
            ),
            options={"family-model": "v2", "out": analytics},
            optional_inputs=("ai-judgments",),
            expectations=(
                (
                    analytics / "creative_families_report.json",
                    "family_schema_version",
                    "creative-family-v2",
                ),
                (
                    analytics / "creative_families_report.json",
                    "ai_judgments_source",
                    str(ai_judgments) if ai_judgments.exists() else None,
                ),
            ),
        ),
        _stage(
            "propagation",
            "analyze_propagation",
            {
                "members": analytics / "creative_family_members.parquet",
                "analysis": master / "creative_analysis.parquet",
                "performance": analytics / "post_performance.parquet",
            },
            outputs(
                analytics,
                "family_account_entries.parquet",
                "cross_account_propagation.parquet",
                "account_propagation_edges.parquet",
                "account_sequence_edges.parquet",
                "account_role_evidence.parquet",
                "propagation_report.json",
            ),
            options={"out": analytics},
        ),
        _stage(
            "timeline",
            "analyze_timeline",
            {
                "posts": master / "posts.parquet",
                "analysis": master / "creative_analysis.parquet",
                "performance": analytics / "post_performance.parquet",
                "cadence": analytics / "posting_cadence.parquet",
                "family-members": analytics / "creative_family_members.parquet",
                "family-entries": analytics / "family_account_entries.parquet",
            },
            outputs(
                analytics,
                "strategy_windows.parquet",
                "strategy_window_members.parquet",
                "strategy_change_points.parquet",
                "strategy_timeline_report.json",
            ),
            options={"timezone": config.timezone, "out": analytics},
            expectations=(
                (analytics / "strategy_timeline_report.json", "timezone", config.timezone),
            ),
        ),
        _stage(
            "patterns",
            "discover_patterns",
            {
                "analysis": master / "creative_analysis.parquet",
                "performance": analytics / "post_performance.parquet",
                "cadence": analytics / "posting_cadence.parquet",
                "families": analytics / "creative_families.parquet",
                "family-members": analytics / "creative_family_members.parquet",
                "propagation": analytics / "cross_account_propagation.parquet",
                "role-evidence": analytics / "account_role_evidence.parquet",
                "strategy-changes": analytics / "strategy_change_points.parquet",
                "strategy-members": analytics / "strategy_window_members.parquet",
            },
            outputs(
                analytics,
                "patterns.parquet",
                "pattern_evidence_links.parquet",
                "patterns_report.json",
            ),
            options={"out": analytics},
        ),
        _stage(
            "strategies",
            "infer_strategies",
            {
                "patterns": analytics / "patterns.parquet",
                "pattern-evidence": analytics / "pattern_evidence_links.parquet",
            },
            outputs(
                analytics,
                "strategy_hypotheses.parquet",
                "account_strategy_hypotheses.parquet",
                "operator_strategy_hypotheses.parquet",
                "strategy_pattern_links.parquet",
                "strategy_evidence_links.parquet",
                "strategy_hypotheses_report.json",
            ),
            options={"out": analytics},
        ),
        _stage(
            "knowledge",
            "promote_knowledge",
            {
                "hypotheses": analytics / "strategy_hypotheses.parquet",
                "strategy-evidence": analytics / "strategy_evidence_links.parquet",
                "families": analytics / "creative_families.parquet",
                "family-members": analytics / "creative_family_members.parquet",
                **({"reviews": config.reviews} if config.reviews is not None else {}),
            },
            tuple(
                knowledge / f"{name}.{suffix}"
                for name in (
                    "strategies",
                    "rules",
                    "lessons",
                    "templates",
                    "playbooks",
                    "knowledge_catalog",
                    "knowledge_source_links",
                    "knowledge_evidence_links",
                )
                for suffix in ("parquet", "jsonl")
            )
            + (knowledge / "knowledge_report.json",),
            options={"out": knowledge},
            expectations=(
                (
                    knowledge / "knowledge_report.json",
                    "reviews_source",
                    str(config.reviews) if config.reviews is not None else None,
                ),
                (
                    knowledge / "knowledge_report.json",
                    "knowledge_schema_version",
                    "operator-knowledge-v2",
                ),
            ),
        ),
        _stage(
            "workspace",
            "build_intelligence_workspace",
            {name.replace("_", "-"): root / path for name, path in WORKSPACE_INPUTS.items()},
            outputs(workspace, *REQUIRED_DATA_FILES, *STATIC_FILES),
            options={"out": workspace, "raw-root": root / "data/00_raw/apify"},
            extra_inputs=tuple(
                Path(__file__).parents[1] / "workspaces" / "assets" / "lab" / name
                for name in STATIC_FILES
            ),
            expectations=(
                (
                    workspace / "workspace.json",
                    "workspace_schema_version",
                    WORKSPACE_SCHEMA_VERSION,
                ),
            ),
        ),
    ]
    # Audit consumes table data and stage reports: provenance-only changes also invalidate it.
    audit_inputs = (
        tuple(
            dict.fromkeys(
                path for spec in specs[:-1] for path in spec.outputs if path.suffix != ".jsonl"
            )
        )
        + specs[-1].outputs
    )
    specs.extend(
        (
            _stage(
                "audit",
                "quality_audit",
                {},
                (config.quality_out,),
                options={
                    "root": root,
                    "operators": config.operators,
                    "timezone": config.timezone,
                    "workspace": workspace,
                    "out": config.quality_out,
                    "reviews": config.reviews,
                },
                extra_inputs=audit_inputs
                + (config.operators,)
                + ((config.reviews,) if config.reviews is not None else ()),
            ),
            _stage(
                "outcome",
                "outcome_audit",
                {},
                (workspace / "outcome_acceptance_report.json",),
                options={
                    "workspace": workspace,
                    "out": workspace / "outcome_acceptance_report.json",
                },
                extra_inputs=tuple(workspace / name for name in OUTCOME_INPUTS.values()),
            ),
        )
    )
    return tuple(specs)


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
            raise ValueError(f"Unknown from-stage {from_stage!r}; expected one of {names}")
        start = names.index(from_stage)
    if through_stage is not None:
        if through_stage not in names:
            raise ValueError(f"Unknown through-stage {through_stage!r}; expected one of {names}")
        end = names.index(through_stage) + 1
    if start >= end:
        raise ValueError("from-stage must not come after through-stage")
    return specs[start:end]


def stage_freshness(spec: StageSpec) -> tuple[str, str]:
    missing_inputs = [path for path in spec.inputs if not path.is_file()]
    if missing_inputs:
        rendered = ", ".join(str(path) for path in missing_inputs[:4])
        suffix = " ..." if len(missing_inputs) > 4 else ""
        return "blocked", f"missing inputs: {rendered}{suffix}"

    missing_outputs = [path for path in spec.outputs if not path.is_file()]
    if missing_outputs:
        rendered = ", ".join(str(path) for path in missing_outputs[:4])
        suffix = " ..." if len(missing_outputs) > 4 else ""
        return "run", f"missing outputs: {rendered}{suffix}"

    if spec.execution_marker is not None and spec.execution_marker.exists():
        return "run", "previous execution did not finish; rebuild from its checkpoint"

    for report_path, key, expected in spec.report_expectations:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "run", f"cannot verify stage parameters from {report_path}"
        if not isinstance(payload, dict):
            return "run", f"cannot verify stage parameters from {report_path}"
        if payload.get(key) != expected:
            return "run", f"stage parameter {key} changed from {payload.get(key)!r} to {expected!r}"

    newest_input = max((path.stat().st_mtime_ns for path in spec.inputs), default=0)
    oldest_output = min((path.stat().st_mtime_ns for path in spec.outputs), default=0)
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
        missing_inputs = {path for path in spec.inputs if not path.is_file()}
        dependency_will_change = any(path in planned_outputs for path in spec.inputs)
        if action == "blocked" and missing_inputs.issubset(planned_outputs):
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


class PipelineExecutionError(RuntimeError):
    """A failed build retains completed stage results for the CLI report."""

    def __init__(self, message: str, results: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.results = results


def execute_pipeline(
    specs: tuple[StageSpec, ...],
    plans: tuple[StagePlan, ...],
    *,
    dry_run: bool = False,
    root: Path | None = None,
    runner: Callable[[str, tuple[str, ...]], None] | None = None,
) -> list[dict[str, str]]:
    if [spec.name for spec in specs] != [plan.name for plan in plans]:
        raise ValueError("Pipeline plans must match selected stages in order")
    if len({spec.name for spec in specs}) != len(specs):
        raise ValueError("Pipeline stage names must be unique")
    if any(plan.action not in {"run", "skip", "blocked"} for plan in plans):
        raise ValueError("Unknown pipeline plan action")
    blocked = [plan for plan in plans if plan.action == "blocked"]
    if blocked and not dry_run:
        raise FileNotFoundError(
            "Pipeline is blocked before execution:\n"
            + "\n".join(f"Stage {plan.name}: {plan.reason}" for plan in blocked)
        )

    results: list[dict[str, str]] = []
    for index, (spec, plan) in enumerate(zip(specs, plans, strict=True), 1):
        result = {"stage": spec.name, "reason": plan.reason}
        if dry_run or plan.action == "skip":
            result["status"] = {
                "run": "would_run",
                "skip": "reused",
                "blocked": "blocked",
            }[plan.action]
            results.append(result)
            logger.debug("stage_reused_or_planned", extra={"context": result})
            continue
        started = time.monotonic()
        context = {"stage": spec.name, "step": index, "total": len(specs)}
        logger.info("stage_started", extra={"context": context})
        try:
            if spec.execution_marker is not None:
                write_json(spec.execution_marker, {**context, "status": "running"}, mode=0o600)
            try:
                if runner is None:
                    with project_context(root):
                        import_module(spec.module).run(**spec.parameters)
                else:
                    runner(spec.module, spec.args)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise RuntimeError(f"{spec.module} exited with status {exc.code}") from exc
            missing = [path for path in spec.outputs if not path.is_file()]
            if missing:
                raise RuntimeError(
                    "completed without required outputs: "
                    + ", ".join(str(path) for path in missing)
                )
            if spec.execution_marker is not None:
                spec.execution_marker.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("stage_failed", extra={"context": {**context, "error": str(exc)}})
            results.append({**result, "status": "failed", "error": str(exc)})
            raise PipelineExecutionError(f"Stage {spec.name} failed: {exc}", results) from exc
        results.append({**result, "status": "rebuilt"})
        logger.info(
            "stage_complete",
            extra={"context": {**context, "seconds": round(time.monotonic() - started, 3)}},
        )
    return results
