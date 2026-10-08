"""The AI readiness audit never calls a model or requires credentials."""
from __future__ import annotations

import json
from pathlib import Path

from creative_research.stages.ai_research_audit import audit_ai_readiness
from test_ai_research import corpus_fixture


def test_ai_readiness_checks_all_review_sources_and_playbook(tmp_path: Path) -> None:
    workspace = corpus_fixture(tmp_path)
    report = audit_ai_readiness(workspace)
    assert report["status"] == "pass"
    assert report["targets_checked"] == 5
    assert report["targets_ready"] == 5
    assert report["targets_failed"] == 0
    assert {x["mode"] for x in report["results"]} == {
        "investigate", "draft_playbook", "stress_test",
    }
    assert all(x["prompt_chars"] <= x["max_prompt_chars"] for x in report["results"])
    assert all(x["evidence_count"] > 0 for x in report["results"])


def test_ai_readiness_finds_broken_post_lineage_before_paid_calls(
    tmp_path: Path,
) -> None:
    workspace = corpus_fixture(tmp_path)
    path = workspace / "evidence.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["posts"] = [r for r in data["posts"] if r["post_uid"] != "P2"]
    path.write_text(json.dumps(data), encoding="utf-8")
    report = audit_ai_readiness(workspace)
    assert report["status"] == "fail"
    assert report["targets_failed"] > 0
    assert any(
        any(code in entry["issues"] for code in (
            "selected_flow_missing_source_post", "family_member_post_missing"
        ))
        for entry in report["results"]
    )
