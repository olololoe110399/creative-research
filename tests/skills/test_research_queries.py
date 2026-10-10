"""Full-population and source-linked research queries must be read-only and honest."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


class Tables:
    def __init__(self, tables: dict[str, pd.DataFrame]) -> None:
        self.tables = tables
        self.sources: list[str] = []

    def load(self, relative: str) -> pd.DataFrame:
        self.sources.append(relative)
        if relative not in self.tables:
            raise ValueError(f"Missing table {relative}")
        return self.tables[relative].copy()


@pytest.fixture
def queries(skill_modules):
    return importlib.import_module("research_queries")


@pytest.fixture
def corpus() -> dict[str, pd.DataFrame]:
    count = 240  # Must exceed the original bridge's 100 raw-row limit.
    performance = pd.DataFrame(
        {
            "post_uid": [f"P{i}" for i in range(count)],
            "operator_id": ["OP1"] * count,
            "account_id": [f"A{i % 3}" for i in range(count)],
            "content_type": ["video"] * count,
            "created_at": ["2026-01-10T00:00:00Z"] * count,
            "views": [float(i + 1) for i in range(count)],
            "views_vs_account_median": [(i + 1) / 50.0 for i in range(count)],
            "views_percentile_account": [i / count for i in range(count)],
            "save_rate_by_view": [0.1 if i % 2 else 0.01 for i in range(count)],
        }
    )
    analysis = pd.DataFrame(
        {
            "post_uid": [f"P{i}" for i in range(count)],
            "topic": ["study"] * count,
            "content_angle": ["how_to"] * count,
            "hook_technique": ["question" if i % 2 else "list_or_number" for i in range(count)],
            "hook_psychological_trigger": ["curiosity"] * count,
            "content_format": ["tutorial"] * count,
            "video_format": ["talking_head"] * count,
            "dominant_visual_type": ["face"] * count,
            "visual_aesthetic": ["natural"] * count,
            "pacing": ["fast"] * count,
            "cta_type": ["save"] * count,
            "narrative_structure": ['["hook","proof","cta"]'] * count,
            "attention_mechanisms": ['["curiosity"]'] * count,
        }
    )
    members = pd.DataFrame(
        {
            "family_id": ["F1"] * count,
            "post_uid": [f"P{i}" for i in range(count)],
            "operator_id": ["OP1"] * count,
            "account_id": [f"A{i % 3}" for i in range(count)],
            "created_at": ["2026-01-10T00:00:00Z"] * count,
            "family_member_index": list(range(1, count + 1)),
            "match_score_to_origin": [i / count for i in range(count)],
            "views_percentile_account": [i / count for i in range(count)],
            "topic": ["stale_member_copy"] * count,
        }
    )
    return {
        "data/06_analytics/post_performance.parquet": performance,
        "data/05_master/creative_analysis.parquet": analysis,
        "data/06_analytics/creative_family_members.parquet": members,
        "data/06_analytics/creative_families.parquet": pd.DataFrame(
            [{"family_id": "F1", "operator_id": "OP1", "member_count": count}]
        ),
        "data/05_master/creative_sequence.parquet": pd.DataFrame(
            [
                {"post_uid": f"P{i}", "position": position, "role": role}
                for i in range(count)
                for position, role in enumerate(("hook", "proof", "cta"), 1)
            ]
        ),
    }


def test_compare_cohorts_aggregates_beyond_100(queries, corpus):
    args = queries.parser().parse_args(
        [
            "--root",
            "/tmp",
            "compare-cohorts",
            "--group-by",
            "hook_technique",
            "--values",
            "question,list_or_number",
        ]
    )
    report = queries.compare_cohorts(args, Tables(corpus))
    assert report["cohort_posts"] == 240
    assert report["population_metric_observed"] == 240
    assert {group["posts"] for group in report["groups"]} == {120}
    assert report["all_eligible_rows_aggregated"]
    assert report["groups_omitted"] == 0


def test_trace_family_pages_details_but_summarizes_all_members(queries, corpus):
    args = queries.parser().parse_args(
        [
            "--root",
            "/tmp",
            "trace-family",
            "--family-id",
            "F1",
            "--offset",
            "200",
            "--limit",
            "20",
            "--beats",
            "2",
        ]
    )
    report = queries.trace_family(args, Tables(corpus))
    assert report["total_matching_members"] == 240
    assert report["all_members_aggregated"]
    assert report["page"]["next_offset"] == 220
    assert report["page"]["returned"] == 20
    assert report["members"][0]["post_uid"] == "P200"
    assert report["members"][0]["evidence"]["topic"] == "study"
    assert report["members"][0]["sequence_total"] == 3
    assert report["members"][0]["sequence_beats_omitted"] == 1
    assert report["dimensions"]["hook_technique"]["observed"] == 240
    assert report["source_rows_missing"] == {"creative_analysis": 0, "post_performance": 0}


def test_missing_metric_and_requested_cohort_are_not_zero(queries, corpus):
    corpus["data/06_analytics/post_performance.parquet"].loc[0, "save_rate_by_view"] = float("nan")
    args = queries.parser().parse_args(
        [
            "--root",
            "/tmp",
            "compare-cohorts",
            "--group-by",
            "content_type",
            "--metric",
            "save_rate_by_view",
            "--values",
            "video,slideshow",
        ]
    )
    report = queries.compare_cohorts(args, Tables(corpus))
    assert report["requested_values_missing"] == ["slideshow"]
    assert report["population_metric_observed"] == 239
    assert report["groups"][0]["missing_metric"] == 1


def test_duplicate_canonical_identity_is_rejected(queries, corpus):
    name = "data/06_analytics/post_performance.parquet"
    frame = corpus[name]
    corpus[name] = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    args = queries.parser().parse_args(
        ["--root", "/tmp", "compare-cohorts", "--group-by", "content_type"]
    )
    with pytest.raises(queries.ResearchError, match="duplicate IDs"):
        queries.compare_cohorts(args, Tables(corpus))


def test_bridge_runs_both_new_commands_without_editing_corpus(
    skill_modules, queries, corpus, tmp_path, capsys, monkeypatch
):
    bridge, _, _ = skill_modules
    for relative, frame in corpus.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
    protected = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setenv("APIFY_TOKEN", "must-not-be-forwarded")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-forwarded")
    for cmd in (
        ["compare-cohorts", "--group-by", "hook_technique", "--operator-id", "OP1"],
        ["trace-family", "--family-id", "F1", "--offset", "200", "--limit", "20"],
    ):
        assert bridge.main(["--root", str(tmp_path), "--python", sys.executable, *cmd]) == 0
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["exit_code"] == 0 and not envelope["truncated"]
        assert envelope["untrusted_output"]
        result = json.loads(envelope["stdout"])
        assert result["command"] == cmd[0]
    assert all(
        (tmp_path / relative).read_bytes() == content for relative, content in protected.items()
    )


def test_bridge_refuses_extra_flags_and_source_escape(skill_modules, queries, tmp_path):
    bridge, _, _ = skill_modules
    for options in (
        ["compare-cohorts", "--group-by", "topic", "--out", "private.json"],
        ["compare-cohorts", "--group-by", "topic", "--execute"],
        ["trace-family", "--family-id", "../../etc"],
        ["trace-family", "--family-id", "F1", "--limit", "101"],
    ):
        if options[0] == "trace-family" and options[2] == "../../etc":
            ns = bridge.build_parser().parse_args(["--root", str(tmp_path), *options])
            with pytest.raises(bridge.BridgeError, match="Invalid family_id"):
                bridge.command_arguments(ns, tmp_path)
        else:
            with pytest.raises(SystemExit):
                bridge.build_parser().parse_args(["--root", str(tmp_path), *options])
    sources = queries.SourceTables(tmp_path)
    with pytest.raises(queries.ResearchError, match="Unsafe"):
        sources.load("../outside.parquet")


def test_taxonomy_has_all_axes_and_linked_outputs():
    root = Path(__file__).resolve().parents[2] / "skills/creative-research"
    guide = (root / "references/creative-taxonomy.md").read_text()
    for axis in (
        "Topic",
        "Hook",
        "Narrative structure",
        "Attention mechanism",
        "Visual format",
        "Pacing",
        "CTA",
    ):
        assert axis in guide
    assert (root / "assets/creative-mechanic-audit.md").is_file()
