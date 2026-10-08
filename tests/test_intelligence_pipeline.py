from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from creative_research.intelligence_pipeline import (
    PipelineConfig,
    StageSpec,
    execute_pipeline,
    plan_pipeline,
    slice_specs,
    stage_freshness,
)
from creative_research.stages.quality_audit import build_quality_report


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    assert "upstream" in plans[1].reason


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
    strategy_pattern_links = pd.DataFrame(
        [{"hypothesis_id": "STR1", "pattern_id": "PAT1"}]
    )
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
    knowledge = pd.DataFrame(
        [{"knowledge_id": "K1", "knowledge_status": "promoted"}]
    )
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
