"""Regression coverage for portable AI discovery tools and the offline evidence-only profile."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from creative_research.pipeline.demo_data import seed_demo


@pytest.fixture
def tools(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "skills/creative-research/scripts"))
    return (
        importlib.import_module("creative_intelligence"),
        importlib.import_module("run_cli"),
        importlib.import_module("research_queries"),
    )


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "project"
    (root / "data/05_master").mkdir(parents=True)
    (root / "data/06_analytics").mkdir(parents=True)
    perf = []
    analysis = []
    sequence = []
    for index in range(240):
        uid = f"POST-{index:04d}"
        hook = "how_to" if index < 140 else "bold_claim"
        content_type = "slideshow" if index < 200 else "video"
        perf.append(
            {
                "post_uid": uid,
                "account_id": "A" if index % 2 else "B",
                "operator_id": "OP1",
                "content_type": content_type,
                "created_at": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=index),
                "views_vs_account_median": 2.0 if hook == "how_to" else 0.5,
                "views": 100 + index,
            }
        )
        analysis.append(
            {
                "post_uid": uid,
                "topic": f"topic-{index % 7}",
                "hook_technique": hook,
                "content_format": "listicle",
                "cta_type": "save",
                "dominant_visual_type": "notes",
                "pacing": "fast",
                "narrative_structure": '["hook","proof","cta"]',
                "attention_mechanisms": '["curiosity","contrast"]',
                "hook_psychological_trigger": "specificity",
            }
        )
        sequence.append(
            {
                "post_uid": uid,
                "position": 1,
                "role": "hook",
                "overlay_text": "An observed opening",
            }
        )
    pd.DataFrame(perf).to_parquet(root / "data/06_analytics/post_performance.parquet")
    pd.DataFrame(analysis).to_parquet(root / "data/05_master/creative_analysis.parquet")
    pd.DataFrame(sequence).to_parquet(root / "data/05_master/creative_sequence.parquet")
    return root


def test_mechanic_groups_span_topics_and_more_than_100_posts(tools, evidence):
    engine, _, _ = tools
    args = engine.parser().parse_args(
        [
            "--root",
            str(evidence),
            "mechanic-groups",
            "--content-type",
            "slideshow",
            "--min-posts",
            "5",
        ]
    )
    result = engine.mechanic_groups(args, engine.Sources(evidence))
    assert result["population_posts"] == 200
    assert result["all_rows_considered"]
    assert sum(group["posts"] for group in result["groups"]) == 200
    group = next(row for row in result["groups"] if row["posts"] == 140)
    assert group["distinct_topics"] == 7
    assert group["metric"] if "metric" in group else True
    assert group["median"] == 2.0


def test_mechanic_trace_pages_without_losing_full_size(tools, evidence):
    engine, _, _ = tools
    root = str(evidence)
    args = engine.parser().parse_args(["--root", root, "mechanic-groups"])
    groups = engine.mechanic_groups(args, engine.Sources(evidence))["groups"]
    ident = next(row["mechanic_id"] for row in groups if row["posts"] == 140)
    traced = engine.parser().parse_args(
        [
            "--root",
            root,
            "trace-mechanic",
            "--mechanic-id",
            ident,
            "--limit",
            "3",
            "--offset",
            "3",
            "--beats",
            "1",
        ]
    )
    result = engine.trace_mechanic(traced, engine.Sources(evidence))
    assert result["total_matching_members"] == 140
    assert result["page"]["next_offset"] == 6
    assert len(result["members"]) == 3
    assert result["members"][0]["sequence_beats"][0]["role"] == "hook"


def test_verify_pattern_uses_all_posts_and_content_type_control(tools, evidence):
    engine, _, _ = tools
    args = engine.parser().parse_args(
        [
            "--root",
            str(evidence),
            "verify-pattern",
            "--content-type",
            "slideshow",
            "--when",
            "hook_technique=how_to",
        ]
    )
    result = engine.verify_pattern(args, engine.Sources(evidence))
    assert result["population_posts"] == 200
    assert result["target"]["posts"] == 140
    assert result["comparison"]["posts"] == 60
    assert result["target"]["median"] == 2
    assert result["comparison"]["median"] == 0.5
    assert result["disposition"] == "descriptive_association_only"
    assert result["exploratory_multiple_testing_warning"]


def test_verify_pattern_cannot_upgrade_singleton_to_supported(tools, evidence):
    engine, _, _ = tools
    args = engine.parser().parse_args(
        [
            "--root",
            str(evidence),
            "verify-pattern",
            "--when",
            "topic=topic-0",
            "--when",
            "hook_technique=bold_claim",
            "--min-posts",
            "100",
        ]
    )
    result = engine.verify_pattern(args, engine.Sources(evidence))
    assert result["disposition"] == "insufficient_evidence"


def test_trace_strategy_uses_existing_evidence_links(tools, evidence):
    engine, _, _ = tools
    folder = evidence / "data/06_analytics"
    pd.DataFrame(
        [
            {
                "hypothesis_id": "H1",
                "hypothesis_type": "temporal_strategy_shift",
                "claim": "Observed shift",
                "confidence_band": "medium",
                "confidence_score": 0.7,
                "causal_claim": False,
            }
        ]
    ).to_parquet(folder / "strategy_hypotheses.parquet")
    pd.DataFrame(
        [
            {
                "hypothesis_id": "H1",
                "pattern_id": "P1",
                "relation": "support",
            }
        ]
    ).to_parquet(folder / "strategy_pattern_links.parquet")
    pd.DataFrame(
        [
            {
                "hypothesis_id": "H1",
                "pattern_id": "P1",
                "relation": "support",
                "post_uid": f"POST-{i:04d}",
                "account_id": "A",
            }
            for i in range(150)
        ]
    ).to_parquet(folder / "strategy_evidence_links.parquet")
    pd.DataFrame(
        [
            {
                "pattern_id": "P1",
                "pattern_type": "strategy_change_point",
                "title": "Observed difference",
                "sample_size": 150,
            }
        ]
    ).to_parquet(folder / "patterns.parquet")
    args = engine.parser().parse_args(
        [
            "--root",
            str(evidence),
            "trace-strategy",
            "--hypothesis-id",
            "H1",
            "--offset",
            "100",
            "--limit",
            "5",
        ]
    )
    result = engine.trace_strategy(args, engine.Sources(evidence))
    assert result["total_evidence_links"] == 150
    assert result["page"]["next_offset"] == 105
    assert result["pattern_links"][0]["pattern_id"] == "P1"
    assert len(result["evidence"]) == 5


def test_bridge_only_allows_bounded_ai_tools(tools, evidence, capsys):
    _, bridge, _ = tools
    path = str(evidence)
    for name in ("mechanic-groups", "verify-pattern", "trace-mechanic", "trace-strategy"):
        with pytest.raises(SystemExit):
            bridge.build_parser().parse_args(
                [
                    "--root",
                    path,
                    name,
                    "--out",
                    "../private",
                ]
            )
    assert (
        bridge.main(
            [
                "--root",
                path,
                "--python",
                sys.executable,
                "mechanic-groups",
                "--content-type",
                "slideshow",
                "--min-posts",
                "5",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert not output["truncated"]
    assert output["untrusted_output"]
    assert json.loads(output["stdout"])["population_posts"] == 200


def test_compare_cohorts_content_type_is_not_silently_mixed(tools, evidence):
    _, _, queries = tools
    args = queries.parser().parse_args(
        [
            "--root",
            str(evidence),
            "compare-cohorts",
            "--group-by",
            "hook_technique",
            "--content-type",
            "video",
        ]
    )
    result = queries.compare_cohorts(args, queries.SourceTables(evidence))
    assert result["population_posts"] == 40
    assert result["scope"]["content_type"] == "video"


def test_evidence_only_profile_stops_at_timeline_without_lab_writes(tmp_path, capsys):
    from creative_research.cli.commands.intelligence_build import main

    root = tmp_path / "demo"
    seed_demo(root)
    main(["--root", str(root), "--profile", "evidence-only", "--json"])
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "complete"
    assert output["profile"] == "evidence-only"
    assert output["through_stage"] == "timeline"
    assert len(output["stages"]) == 6
    assert (root / "data/06_analytics/evidence_pipeline_report.json").exists()
    assert not (root / "data/07_exports/operator-intelligence").exists()
    assert not (root / "data/06_analytics/patterns.parquet").exists()


def test_evidence_only_refuses_beyond_timeline(tmp_path):
    from creative_research.cli.commands.intelligence_build import main

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--root",
                str(tmp_path),
                "--profile",
                "evidence-only",
                "--through-stage",
                "strategies",
                "--dry-run",
            ]
        )
    assert exc.value.code == 2
