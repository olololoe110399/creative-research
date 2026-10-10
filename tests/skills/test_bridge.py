from __future__ import annotations

import json
import os
import sys
import time

import pandas as pd
import pytest

from creative_research.cli.app import execute


@pytest.fixture
def demo(tmp_path, capsys):
    root = tmp_path / "demo"
    assert execute(["demo", "--out", str(root), "--json"]) == 0
    capsys.readouterr()
    return root


@pytest.mark.parametrize(
    "command",
    ["scrape", "analyze-slides", "analyze-videos", "adopt", "review-knowledge", "demo", "lab"],
)
def test_bridge_rejects_commands_outside_offline_scope(skill_modules, tmp_path, command):
    bridge, _, _ = skill_modules
    with pytest.raises(SystemExit) as error:
        bridge.build_parser().parse_args(["--root", str(tmp_path), command])
    assert error.value.code == 2


@pytest.mark.parametrize(
    "args",
    [
        ["query", "data/x.csv", "--out", "data/y.csv"],
        ["query", "data/x.csv", "--limit", "101"],
        ["status", "--env-file", ".env"],
        ["quality-audit", "--out", "private.json"],
    ],
)
def test_bridge_rejects_arbitrary_output_env_and_unbounded_queries(skill_modules, tmp_path, args):
    bridge, _, _ = skill_modules
    with pytest.raises(SystemExit):
        bridge.build_parser().parse_args(["--root", str(tmp_path), *args])


def test_root_is_required_and_missing_data_is_actionable(skill_modules, tmp_path, capsys):
    bridge, _, _ = skill_modules
    with pytest.raises(SystemExit):
        bridge.build_parser().parse_args(["status"])
    assert bridge.main(["--root", str(tmp_path), "validate"]) == 2
    assert "Missing input" in json.loads(capsys.readouterr().out)["error"]
    assert list(tmp_path.iterdir()) == []


def test_engine_preflight_does_not_install_or_load_credentials(skill_modules, monkeypatch):
    bridge, _, _ = skill_modules
    monkeypatch.setenv("APIFY_TOKEN", "private")
    monkeypatch.setenv("GEMINI_API_KEY", "private")
    monkeypatch.setenv("PYTHONPATH", "unexpected")
    monkeypatch.setenv("CREATIVE_RESEARCH_ROOT", "unexpected")
    env = bridge.clean_environment()
    assert not set(env) & {"APIFY_TOKEN", "GEMINI_API_KEY", "PYTHONPATH", "CREATIVE_RESEARCH_ROOT"}
    monkeypatch.setattr(bridge, "run_process", lambda *args, **kwargs: {"exit_code": 1})
    with pytest.raises(bridge.BridgeError, match="No installation was attempted"):
        bridge.preflight(sys.executable)


def test_query_equality_uses_engine_syntax_and_rejects_silent_empty_cohort(skill_modules, demo):
    bridge, _, _ = skill_modules
    parser = bridge.build_parser()
    for condition in ("operator_id==OP1", "operator_id", "=OP1"):
        ns = parser.parse_args(
            ["--root", str(demo), "query", "data/05_master/posts.parquet", "--where", condition]
        )
        with pytest.raises(bridge.BridgeError, match="single"):
            bridge.command_arguments(ns, demo)
    ns = parser.parse_args(
        ["--root", str(demo), "query", "data/05_master/posts.parquet", "--where", "operator_id=OP1"]
    )
    assert "operator_id=OP1" in bridge.command_arguments(ns, demo)


def test_confined_inputs_reject_escape_symlink_and_private_state(skill_modules, tmp_path):
    bridge, _, _ = skill_modules
    data = tmp_path / "data"
    data.mkdir()
    outside = tmp_path.parent / "outside.csv"
    outside.write_text("post_id,views\n01,10\n")
    (data / "link.csv").symlink_to(outside)
    for value in ("../outside.csv", "data/link.csv"):
        with pytest.raises(bridge.BridgeError, match="inside"):
            bridge._table(tmp_path, value)
    private = data / "operating_state"
    private.mkdir()
    (private / "posts.csv").write_text("private")
    with pytest.raises(bridge.BridgeError, match="Private"):
        bridge._table(tmp_path, "data/operating_state/posts.csv")


def test_build_and_audit_writes_need_explicit_confirmation(skill_modules, demo):
    bridge, _, _ = skill_modules
    parser = bridge.build_parser()
    for command in (["intelligence-build", "--execute"], ["quality-audit"]):
        ns = parser.parse_args(["--root", str(demo), *command])
        with pytest.raises(bridge.BridgeError, match="confirmation"):
            bridge.command_arguments(ns, demo)
    plan = parser.parse_args(["--root", str(demo), "intelligence-build"])
    assert "--dry-run" in bridge.command_arguments(plan, demo)
    (demo / "data/07_exports/operator-intelligence/escape").symlink_to(demo.parent)
    approved = parser.parse_args(["--root", str(demo), "quality-audit", "--approve-write"])
    with pytest.raises(bridge.BridgeError, match="symlinks"):
        bridge.command_arguments(approved, demo)


def test_process_output_is_bounded_redacted_and_times_out(skill_modules):
    bridge, _, _ = skill_modules
    secret = "apify_" + "api_" + "x" * 30
    code = f"import sys; print({secret!r}); print('x' * 5000); print('y' * 5000, file=sys.stderr)"
    result = bridge.run_process([sys.executable, "-I", "-c", code], timeout=5, max_bytes=1024)
    assert result["exit_code"] == 0 and result["truncated"]
    assert secret not in result["stdout"] and "[REDACTED]" in result["stdout"]
    assert len(result["stderr"].encode()) <= 1024
    timeout = bridge.run_process(
        [sys.executable, "-I", "-c", "import time; time.sleep(5)"], timeout=1, max_bytes=1024
    )
    assert timeout["timed_out"] and timeout["exit_code"] == 124


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
@pytest.mark.parametrize("parent_waits", [True, False])
def test_timeout_stops_descendants_holding_output_pipes(skill_modules, parent_waits):
    bridge, _, _ = skill_modules
    code = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])"
    if parent_waits:
        code += "; time.sleep(30)"
    started = time.monotonic()
    result = bridge.run_process([sys.executable, "-I", "-c", code], timeout=1, max_bytes=1024)
    assert result["exit_code"] == 124
    assert time.monotonic() - started < 10


def test_all_supported_commands_work_with_offline_demo_without_source_mutation(
    skill_modules, demo, capsys, monkeypatch
):
    bridge, _, _ = skill_modules
    monkeypatch.setenv("APIFY_TOKEN", "must-not-use")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-use")
    private = demo / "data/07_knowledge/operating_state/sentinel.json"
    private.parent.mkdir(exist_ok=True)
    private.write_text('{"private":"unchanged"}')
    protected = {
        path: path.read_bytes() for path in (demo / "data/05_master").glob("*") if path.is_file()
    }
    protected[private] = private.read_bytes()
    commands = [
        ["status"],
        ["validate"],
        [
            "query",
            "data/06_analytics/post_performance.parquet",
            "--columns",
            "post_uid,views",
            "--where",
            "views>=1000",
            "--limit",
            "2",
        ],
        ["rank-posts", "--top", "2"],
        ["intelligence-build"],
        ["intelligence-build", "--execute", "--approve-write"],
        ["quality-audit", "--approve-write"],
    ]
    for args in commands:
        assert bridge.main(["--root", str(demo), *args]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["untrusted_output"] and not result["truncated"]
        assert result["exit_code"] == 0
        if args == ["intelligence-build"]:
            assert json.loads(result["stdout"])["dry_run"]
    assert all(path.read_bytes() == content for path, content in protected.items())


def test_read_only_bridge_does_not_change_workspace_files(skill_modules, demo, capsys):
    bridge, _, _ = skill_modules
    before = {
        path.relative_to(demo): path.read_bytes() for path in demo.rglob("*") if path.is_file()
    }
    assert bridge.main(["--root", str(demo), "intelligence-build"]) == 0
    capsys.readouterr()
    after = {
        path.relative_to(demo): path.read_bytes() for path in demo.rglob("*") if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize("value", [0.12345678912345678, 0.3333333333333333, 1e-18, 1e21])
def test_query_display_preserves_float_round_trip_without_metric_recalculation(
    skill_modules, tmp_path, capsys, value
):
    bridge, _, _ = skill_modules
    data = tmp_path / "data"
    data.mkdir()
    source = data / "metrics.parquet"
    pd.DataFrame([{"post_uid": "P1", "ratio": value}]).to_parquet(source, index=False)
    before = source.read_bytes()
    assert (
        bridge.main(
            [
                "--root",
                str(tmp_path),
                "query",
                "data/metrics.parquet",
                "--columns",
                "post_uid,ratio",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    printed = result["stdout"].splitlines()[1].split()[-1]
    assert float(printed) == value
    assert source.read_bytes() == before
