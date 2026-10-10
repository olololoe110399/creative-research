from __future__ import annotations

import inspect
import json
import os
from importlib import import_module
from pathlib import Path

import pandas as pd
import pytest

from creative_research.analysis.quality_audit import build_quality_report
from creative_research.pipeline.build import (
    PIPELINE_STAGE_NAMES,
    PipelineConfig,
    PipelineExecutionError,
    StageSpec,
    build_stage_specs,
    execute_pipeline,
    plan_pipeline,
    slice_specs,
    stage_freshness,
)
from creative_research.pipeline.contracts import REQUIRED_DATA_FILES, STATIC_FILES


@pytest.mark.parametrize("stage_index", range(12))
def test_stage_parameters_bind_directly_to_workflow_and_are_immutable(tmp_path, stage_index):
    config = PipelineConfig.from_paths(root=tmp_path)
    spec = build_stage_specs(config)[stage_index]
    assert spec.module.startswith("creative_research.pipeline.steps.")
    inspect.signature(import_module(spec.module).run).bind(**spec.parameters)
    assert all(path.is_file() for path in spec.inputs if "creative_research" in path.parts)
    with pytest.raises(TypeError):
        spec.parameters["unexpected"] = "must-not-change"


def test_default_runner_builds_without_importing_cli_or_mutating_arguments(tmp_path):
    import subprocess
    import sys

    code = """
import os, sys
from pathlib import Path
from creative_research.pipeline.build import PipelineConfig, build_stage_specs, plan_pipeline, execute_pipeline
from creative_research.pipeline.demo_data import seed_demo
root = Path(sys.argv[1])
seed_demo(root)
old_argv, arguments = sys.argv, sys.argv[:]
previous = os.environ.get("CREATIVE_RESEARCH_PROJECT_ROOT")
specs = build_stage_specs(PipelineConfig.from_paths(root=root))
results = execute_pipeline(specs, plan_pipeline(specs), root=root)
assert len(results) == 12 and all(item["status"] == "rebuilt" for item in results)
assert sys.argv is old_argv and sys.argv == arguments
assert os.environ.get("CREATIVE_RESEARCH_PROJECT_ROOT") == previous
assert not any(name.startswith("creative_research.cli") for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_unfinished_stage_is_rebuilt_even_when_existing_outputs_are_fresh(tmp_path) -> None:
    output, marker = tmp_path / "result", tmp_path / ".pipeline/stage.json"
    output.write_text("previous successful output")
    spec = StageSpec("a", "a", (), (output,), (), execution_marker=marker)
    assert stage_freshness(spec)[0] == "skip"

    def fail(*args):
        output.write_text("partially replaced output")
        raise RuntimeError("incomplete stage")

    with pytest.raises(PipelineExecutionError):
        execute_pipeline((spec,), plan_pipeline((spec,), force=True), runner=fail)
    assert marker.is_file()
    assert stage_freshness(spec)[0] == "run"
    execute_pipeline(
        (spec,), plan_pipeline((spec,)), runner=lambda *args: output.write_text("complete")
    )
    assert not marker.exists()
    assert stage_freshness(spec)[0] == "skip"


def test_interrupted_stage_keeps_marker_for_safe_resume(tmp_path) -> None:
    marker = tmp_path / "marker.json"
    spec = StageSpec("a", "a", (), (), (), execution_marker=marker)

    def interrupt(*args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_pipeline((spec,), plan_pipeline((spec,), force=True), runner=interrupt)
    assert marker.exists()


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_stage_freshness_rebuilds_when_report_parameter_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    output = tmp_path / "output"
    report = tmp_path / "report.json"
    _touch(source)
    _touch(output)
    report.write_text('{"timezone": "UTC"}', encoding="utf-8")

    newest = max(source.stat().st_mtime_ns, report.stat().st_mtime_ns)
    os.utime(output, ns=(newest + 10_000, newest + 10_000))

    spec = StageSpec(
        name="cadence",
        module="example",
        inputs=(source,),
        outputs=(output, report),
        args=(),
        report_expectations=((report, "timezone", "Asia/Ho_Chi_Minh"),),
    )
    action, reason = stage_freshness(spec)
    assert action == "run"
    assert "timezone" in reason


def test_stage_freshness_reuses_outputs_until_input_changes(tmp_path: Path) -> None:
    source = tmp_path / "input"
    output = tmp_path / "output"
    _touch(source)
    _touch(output)

    now = output.stat().st_mtime_ns
    os.utime(source, ns=(now - 10_000, now - 10_000))
    os.utime(output, ns=(now, now))

    spec = StageSpec(
        name="x",
        module="example",
        inputs=(source,),
        outputs=(output,),
        args=(),
    )
    assert stage_freshness(spec)[0] == "skip"

    os.utime(source, ns=(now + 10_000, now + 10_000))
    assert stage_freshness(spec)[0] == "run"


def test_pipeline_plan_invalidates_downstream_when_upstream_runs(tmp_path: Path) -> None:
    a_in = tmp_path / "a.in"
    a_out = tmp_path / "a.out"
    b_out = tmp_path / "b.out"
    _touch(a_in)
    _touch(b_out)

    specs = (
        StageSpec("a", "a", (a_in,), (a_out,), ()),
        StageSpec("b", "b", (a_out,), (b_out,), ()),
    )
    plans = plan_pipeline(specs)
    assert [plan.action for plan in plans] == ["run", "run"]
    assert "dependenc" in plans[1].reason


def test_pipeline_only_invalidates_actual_dependents(tmp_path: Path) -> None:
    source_a = tmp_path / "a.in"
    source_b = tmp_path / "b.in"
    a_out = tmp_path / "a.out"
    b_out = tmp_path / "b.out"
    c_out = tmp_path / "c.out"
    for path in (source_a, source_b, a_out, b_out, c_out):
        _touch(path)

    now = c_out.stat().st_mtime_ns
    for path in (a_out, b_out, c_out):
        os.utime(path, ns=(now, now))
    os.utime(source_a, ns=(now + 10_000, now + 10_000))
    os.utime(source_b, ns=(now - 10_000, now - 10_000))

    specs = (
        StageSpec("a", "a", (source_a,), (a_out,), ()),
        StageSpec("b", "b", (source_b,), (b_out,), ()),
        StageSpec("c", "c", (a_out,), (c_out,), ()),
    )
    plans = plan_pipeline(specs)
    assert [plan.action for plan in plans] == ["run", "skip", "run"]


def test_execute_pipeline_dry_run_never_calls_runner(tmp_path: Path) -> None:
    source = tmp_path / "in"
    output = tmp_path / "out"
    _touch(source)
    spec = StageSpec("a", "a", (source,), (output,), ())
    plans = plan_pipeline((spec,))
    calls: list[str] = []

    results = execute_pipeline(
        (spec,),
        plans,
        dry_run=True,
        runner=lambda module, args: calls.append(module),
    )
    assert calls == []
    assert results[0]["status"] == "would_run"


def test_slice_specs_honors_stage_boundaries() -> None:
    specs = tuple(
        StageSpec(name, name, (), (), ())
        for name in ("warehouse", "performance", "cadence", "families")
    )
    sliced = slice_specs(
        specs,
        from_stage="performance",
        through_stage="cadence",
    )
    assert [spec.name for spec in sliced] == ["performance", "cadence"]


def _valid_frames() -> dict[str, pd.DataFrame]:
    operators = pd.DataFrame([{"operator_id": "OP1"}])
    accounts = pd.DataFrame(
        [
            {"account_id": "A", "operator_id": "OP1"},
            {"account_id": "B", "operator_id": "OP1"},
        ]
    )
    posts = pd.DataFrame(
        [
            {"post_uid": "P1", "account_id": "A", "operator_id": "OP1"},
            {"post_uid": "P2", "account_id": "B", "operator_id": "OP1"},
        ]
    )
    analysis = pd.DataFrame([{"post_uid": "P1"}, {"post_uid": "P2"}])
    performance = pd.DataFrame([{"post_uid": "P1"}, {"post_uid": "P2"}])
    cadence = pd.DataFrame([{"post_uid": "P1"}, {"post_uid": "P2"}])
    families = pd.DataFrame([{"family_id": "F1"}])
    family_members = pd.DataFrame(
        [
            {"family_id": "F1", "post_uid": "P1"},
            {"family_id": "F1", "post_uid": "P2"},
        ]
    )
    propagation = pd.DataFrame(
        [
            {
                "family_id": "F1",
                "family_origin_post_uid": "P1",
                "target_first_post_uid": "P2",
                "origin_account_id": "A",
                "target_account_id": "B",
            }
        ]
    )
    patterns = pd.DataFrame([{"pattern_id": "PAT1"}])
    pattern_evidence = pd.DataFrame(
        [
            {
                "pattern_id": "PAT1",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
            }
        ]
    )
    strategies = pd.DataFrame([{"hypothesis_id": "STR1"}])
    strategy_pattern_links = pd.DataFrame([{"hypothesis_id": "STR1", "pattern_id": "PAT1"}])
    strategy_evidence_links = pd.DataFrame(
        [
            {
                "hypothesis_id": "STR1",
                "pattern_id": "PAT1",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
            }
        ]
    )
    knowledge = pd.DataFrame([{"knowledge_id": "K1", "knowledge_status": "promoted"}])
    knowledge_source_links = pd.DataFrame(
        [
            {
                "knowledge_id": "K1",
                "source_type": "hypothesis",
                "source_id": "STR1",
            }
        ]
    )
    knowledge_evidence_links = pd.DataFrame(
        [
            {
                "knowledge_id": "K1",
                "pattern_id": "PAT1",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
            }
        ]
    )
    return locals()


def test_quality_report_passes_complete_lineage() -> None:
    frames = _valid_frames()
    report = build_quality_report(
        operators=frames["operators"],
        accounts=frames["accounts"],
        posts=frames["posts"],
        analysis=frames["analysis"],
        performance=frames["performance"],
        cadence=frames["cadence"],
        families=frames["families"],
        family_members=frames["family_members"],
        propagation=frames["propagation"],
        patterns=frames["patterns"],
        pattern_evidence=frames["pattern_evidence"],
        strategies=frames["strategies"],
        strategy_pattern_links=frames["strategy_pattern_links"],
        strategy_evidence_links=frames["strategy_evidence_links"],
        knowledge=frames["knowledge"],
        knowledge_source_links=frames["knowledge_source_links"],
        knowledge_evidence_links=frames["knowledge_evidence_links"],
        workspace_missing_files=[],
    )
    assert report["status"] == "pass"
    assert report["coverage"]["family_membership_coverage"] == 1.0
    assert report["issue_counts"]["fail"] == 0


def test_quality_report_fails_orphan_lineage_and_low_coverage() -> None:
    frames = _valid_frames()
    frames["analysis"] = pd.DataFrame([{"post_uid": "P1"}])
    frames["family_members"].loc[1, "post_uid"] = "MISSING"
    frames["pattern_evidence"].loc[0, "pattern_id"] = "PAT-MISSING"

    report = build_quality_report(
        operators=frames["operators"],
        accounts=frames["accounts"],
        posts=frames["posts"],
        analysis=frames["analysis"],
        performance=frames["performance"],
        cadence=frames["cadence"],
        families=frames["families"],
        family_members=frames["family_members"],
        propagation=frames["propagation"],
        patterns=frames["patterns"],
        pattern_evidence=frames["pattern_evidence"],
        strategies=frames["strategies"],
        strategy_pattern_links=frames["strategy_pattern_links"],
        strategy_evidence_links=frames["strategy_evidence_links"],
        knowledge=frames["knowledge"],
        knowledge_source_links=frames["knowledge_source_links"],
        knowledge_evidence_links=frames["knowledge_evidence_links"],
        workspace_missing_files=["workspace.json"],
    )
    assert report["status"] == "fail"
    codes = {issue["code"] for issue in report["issues"]}
    assert "lineage.family_member_post_orphan" in codes
    assert "lineage.pattern_evidence_pattern" in codes
    assert "workspace.missing_files" in codes


def test_workspace_pipeline_tracks_production_pack_and_never_requires_retired_ai_ui(
    tmp_path: Path,
) -> None:
    config = PipelineConfig(
        root=tmp_path,
        operators=tmp_path / "config/operators.toml",
        reviews=None,
        timezone="UTC",
        workspace_out=tmp_path / "lab",
        quality_out=tmp_path / "lab/quality_report.json",
    )
    specs = build_stage_specs(config)
    workspace = next(spec for spec in specs if spec.name == "workspace")
    names = {path.name for path in workspace.outputs}
    assert "production.json" in names
    assert "production-kit.zip" in names
    assert "production_ui.js" in names
    assert "ai_ui.js" not in names
    assert "production.json" in {
        p.name for p in next(x for x in specs if x.name == "workspace").outputs
    }


def _config(root: Path, **overrides) -> PipelineConfig:
    return PipelineConfig.from_paths(root=root, **overrides)


def _fresh_outputs(spec: StageSpec) -> None:
    for path in spec.inputs:
        if not path.exists():
            _touch(path)
    reports: dict[Path, dict] = {}
    for path, key, value in spec.report_expectations:
        reports.setdefault(path, {})[key] = value
    newest = max((path.stat().st_mtime_ns for path in spec.inputs), default=0)
    for path in spec.outputs:
        _touch(path, json.dumps(reports.get(path, {})))
        mtime = max(path.stat().st_mtime_ns, newest) + 10_000
        os.utime(path, ns=(mtime, mtime))


def test_config_resolves_paths_against_root_and_keeps_reports_with_workspace(tmp_path) -> None:
    config = _config(tmp_path, workspace_out="exports/lab", reviews="config/reviews.toml")
    assert config.operators == tmp_path / "config/operators.toml"
    assert config.reviews == tmp_path / "config/reviews.toml"
    assert config.workspace_out == tmp_path / "exports/lab"
    assert config.quality_out == tmp_path / "exports/lab/quality_report.json"
    custom = _config(tmp_path, quality_out="reports/custom.json")
    assert custom.quality_out == tmp_path / "reports/custom.json"


def test_config_rejects_invalid_timezone_before_running_stages(tmp_path) -> None:
    with pytest.raises(ValueError, match="Unknown timezone"):
        _config(tmp_path, timezone="Not/A-Timezone")


def test_stage_contracts_have_consistent_order_inputs_and_workspace_files(tmp_path) -> None:
    specs = build_stage_specs(_config(tmp_path, reviews="config/reviews.toml"))
    assert tuple(spec.name for spec in specs) == PIPELINE_STAGE_NAMES
    all_outputs = [path for spec in specs for path in spec.outputs]
    assert len(all_outputs) == len(set(all_outputs))
    produced: set[Path] = set()
    for spec in specs:
        # A generated input can only come from a preceding stage.
        assert not (set(spec.inputs) & set(all_outputs) - produced)
        produced.update(spec.outputs)
    workspace = next(spec for spec in specs if spec.name == "workspace")
    assert {path.name for path in workspace.outputs} == set(REQUIRED_DATA_FILES + STATIC_FILES)
    assert all(path.is_absolute() for spec in specs for path in (*spec.inputs, *spec.outputs))
    for spec in specs:
        for path in spec.inputs:
            if path.suffix == ".parquet" or path.name == "reviews.toml":
                assert str(path) in spec.args or spec.name in {"audit", "outcome"}


def test_workspace_freshness_tracks_packaged_static_assets(tmp_path) -> None:
    spec = next(s for s in build_stage_specs(_config(tmp_path)) if s.name == "workspace")
    assert {p.name for p in spec.inputs if p.suffix in {".js", ".css", ".html", ".svg"}} == set(
        STATIC_FILES
    )
    _fresh_outputs(spec)
    assert stage_freshness(spec)[0] == "skip"
    # Backdate a generated asset, leaving the actual package source untouched.
    source_asset = next(p for p in spec.inputs if p.name == "app.js")
    generated_asset = next(p for p in spec.outputs if p.name == "app.js")
    older = source_asset.stat().st_mtime_ns - 10_000
    os.utime(generated_asset, ns=(older, older))
    assert stage_freshness(spec)[0] == "run"


def test_removing_optional_ai_judgments_invalidates_family_provenance(tmp_path) -> None:
    judgments = tmp_path / "data/06_analytics/family_ai/family_ai_judgments.parquet"
    _touch(judgments)
    spec = next(s for s in build_stage_specs(_config(tmp_path)) if s.name == "families")
    _fresh_outputs(spec)
    assert stage_freshness(spec)[0] == "skip"
    judgments.unlink()
    without_ai = next(s for s in build_stage_specs(_config(tmp_path)) if s.name == "families")
    action, reason = stage_freshness(without_ai)
    assert action == "run"
    assert "ai_judgments_source" in reason


@pytest.mark.parametrize("report_value", ["[]", "null", "broken json"])
def test_unverifiable_report_is_stale_not_an_exception(tmp_path, report_value) -> None:
    output = tmp_path / "report.json"
    _touch(output, report_value)
    spec = StageSpec("x", "x", (), (output,), (), ((output, "schema", "v1"),))
    assert stage_freshness(spec)[0] == "run"


def test_freshness_handles_source_free_stage_and_rejects_directory_output(tmp_path) -> None:
    output = tmp_path / "out"
    _touch(output)
    spec = StageSpec("x", "x", (), (output,), ())
    assert stage_freshness(spec)[0] == "skip"
    output.unlink()
    output.mkdir()
    assert stage_freshness(spec)[0] == "run"


def test_preflight_blocks_entire_run_before_any_stage_writes(tmp_path) -> None:
    source = tmp_path / "source"
    _touch(source)
    specs = (
        StageSpec("a", "a", (source,), (tmp_path / "a.out",), ()),
        StageSpec("b", "b", (tmp_path / "missing",), (tmp_path / "b.out",), ()),
    )
    calls = []
    with pytest.raises(FileNotFoundError, match="before execution"):
        execute_pipeline(specs, plan_pipeline(specs), runner=lambda *args: calls.append(args))
    assert calls == []
    results = execute_pipeline(specs, plan_pipeline(specs), dry_run=True)
    assert [result["status"] for result in results] == ["would_run", "blocked"]
    assert not (tmp_path / "a.out").exists()


def test_failed_stage_keeps_partial_results_and_stops_dependents(tmp_path) -> None:
    specs = (
        StageSpec("a", "a", (), (tmp_path / "a.out",), ()),
        StageSpec("b", "b", (tmp_path / "a.out",), (tmp_path / "b.out",), ()),
        StageSpec("c", "c", (tmp_path / "b.out",), (tmp_path / "c.out",), ()),
    )
    calls = []

    def runner(module, args):
        calls.append(module)
        if module == "a":
            _touch(tmp_path / "a.out")
        else:
            raise SystemExit(2)

    with pytest.raises(PipelineExecutionError, match="Stage b failed") as error:
        execute_pipeline(specs, plan_pipeline(specs), runner=runner)
    assert calls == ["a", "b"]
    assert [r["status"] for r in error.value.results] == ["rebuilt", "failed"]
    assert "status 2" in error.value.results[-1]["error"]


def test_runner_must_produce_required_files(tmp_path) -> None:
    spec = StageSpec("a", "a", (), (tmp_path / "missing",), ())
    with pytest.raises(PipelineExecutionError, match="without required outputs"):
        execute_pipeline((spec,), plan_pipeline((spec,)), runner=lambda *args: None)


def test_mismatched_plan_cannot_run_the_wrong_stage() -> None:
    spec = StageSpec("a", "a", (), (), ())
    other = StageSpec("b", "b", (), (), ())
    with pytest.raises(ValueError, match="match selected stages"):
        execute_pipeline((spec,), plan_pipeline((other,)))
