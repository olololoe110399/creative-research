from __future__ import annotations

import json

import pytest

from creative_research.cli.commands import intelligence_build, quality_audit
from creative_research.pipeline.build import (
    PipelineExecutionError,
    StageSpec,
)


def test_dry_run_reports_missing_inputs_without_writing(tmp_path, capsys) -> None:
    intelligence_build.main(["--root", str(tmp_path), "--dry-run", "--workspace-out", "lab"])
    output = capsys.readouterr().out
    assert '"status": "blocked"' in output
    assert "creative_master.parquet" in output
    assert not (tmp_path / "lab").exists()


def test_later_stage_only_requires_its_actual_inputs(tmp_path, monkeypatch) -> None:
    source = tmp_path / "existing-intermediate.json"
    source.write_text("{}", encoding="utf-8")
    output = tmp_path / "lab/workspace.json"
    spec = StageSpec("workspace", "example", (source,), (output,), ())
    monkeypatch.setattr(intelligence_build, "build_stage_specs", lambda _: (spec,))

    def execute(specs, plans, **kwargs):
        assert kwargs["root"] == tmp_path
        output.parent.mkdir()
        output.write_text("{}", encoding="utf-8")
        return [{"stage": "workspace", "status": "rebuilt"}]

    monkeypatch.setattr(intelligence_build, "execute_pipeline", execute)
    intelligence_build.main(
        [
            "--root",
            str(tmp_path),
            "--from-stage",
            "workspace",
            "--workspace-out",
            "lab",
        ]
    )
    report = json.loads((tmp_path / "lab/pipeline_report.json").read_text())
    assert report["status"] == "complete"
    assert report["quality_out"] == str(tmp_path / "lab/quality_report.json")
    assert not (tmp_path / "data/05_master/creative_master.parquet").exists()
    assert not (tmp_path / "config/operators.toml").exists()


def test_failed_build_writes_diagnostic_report_in_custom_workspace(tmp_path, monkeypatch) -> None:
    spec = StageSpec("warehouse", "example", (), (tmp_path / "artifact",), ())
    monkeypatch.setattr(intelligence_build, "build_stage_specs", lambda _: (spec,))

    def fail(*args, **kwargs):
        raise PipelineExecutionError("broken stage", [{"stage": "warehouse", "status": "failed"}])

    monkeypatch.setattr(intelligence_build, "execute_pipeline", fail)
    with pytest.raises(SystemExit) as error:
        intelligence_build.main(["--root", str(tmp_path), "--workspace-out", "lab"])
    assert error.value.code == 1
    report = json.loads((tmp_path / "lab/pipeline_report.json").read_text())
    assert report["status"] == "failed"
    assert report["error"] == "broken stage"
    assert report["stages"][0]["status"] == "failed"


def test_invalid_timezone_is_rejected_before_creating_any_output(tmp_path) -> None:
    with pytest.raises(SystemExit) as error:
        intelligence_build.main(["--root", str(tmp_path), "--timezone", "bad/timezone"])
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_quality_audit_uses_active_root_and_custom_workspace_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(SystemExit) as error:
        quality_audit.main(["--workspace", "lab"])
    assert error.value.code == 1  # Missing evidence is expected in this empty fixture.
    report = json.loads((tmp_path / "lab/quality_report.json").read_text())
    assert report["root"] == str(tmp_path)
    assert report["workspace"] == str(tmp_path / "lab")


def test_offline_pipeline_builds_then_reuses_all_stages(tmp_path, monkeypatch) -> None:
    """Exercise real stage entrypoints with local synthetic evidence, never providers."""
    from creative_research.pipeline.demo_data import seed_demo

    seed_demo(tmp_path)
    operators = tmp_path / "config/operators.toml"
    master = tmp_path / "data/05_master/creative_master.parquet"
    original_master = master.read_bytes()
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path / "unrelated"))
    args = ["--root", str(tmp_path), "--workspace-out", "lab"]

    intelligence_build.main(args)
    report = json.loads((tmp_path / "lab/pipeline_report.json").read_text())
    assert report["status"] == "complete"
    assert len(report["stages"]) == 12
    assert {stage["status"] for stage in report["stages"]} == {"rebuilt"}
    assert (tmp_path / "lab/quality_report.json").is_file()
    assert (tmp_path / "lab/outcome_acceptance_report.json").is_file()
    assert master.read_bytes() == original_master

    intelligence_build.main(args)
    reused = json.loads((tmp_path / "lab/pipeline_report.json").read_text())
    assert {stage["status"] for stage in reused["stages"]} == {"reused"}
    from creative_research.infrastructure.paths import project_root

    assert project_root() == tmp_path / "unrelated"

    # A workspace-only rebuild needs intermediate tables, not excluded upstream sources.
    master.unlink()
    operators.unlink()
    intelligence_build.main(
        args + ["--from-stage", "workspace", "--through-stage", "workspace", "--force"]
    )
    sliced = json.loads((tmp_path / "lab/pipeline_report.json").read_text())
    assert sliced["status"] == "complete"
    assert [(stage["stage"], stage["status"]) for stage in sliced["stages"]] == [
        ("workspace", "rebuilt")
    ]
