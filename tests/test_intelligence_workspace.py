from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.intelligence_workspace import (
    REQUIRED_DATA_FILES,
    STATIC_FILES,
    build_workspace_payloads,
    validate_intelligence_workspace,
    write_intelligence_workspace,
)


def _frames() -> dict[str, pd.DataFrame]:
    operators = pd.DataFrame(
        [
            {
                "operator_id": "OP1",
                "name": "Operator One",
                "verified": True,
                "observed_accounts": 2,
                "observed_posts": 2,
            }
        ]
    )
    accounts = pd.DataFrame(
        [
            {
                "operator_id": "OP1",
                "account_id": "A",
                "account": "alpha",
                "observed_posts": 1,
            },
            {
                "operator_id": "OP1",
                "account_id": "B",
                "account": "beta",
                "observed_posts": 1,
            },
        ]
    )
    posts = pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "operator_id": "OP1",
                "account_id": "A",
                "account": "alpha",
                "post_id": "1",
                "url": "https://example.test/1",
                "created_at": "2026-01-01T00:00:00Z",
                "content_type": "slideshow",
                "views": 100,
            },
            {
                "post_uid": "P2",
                "operator_id": "OP1",
                "account_id": "B",
                "account": "beta",
                "post_id": "2",
                "url": "https://example.test/2",
                "created_at": "2026-02-01T00:00:00Z",
                "content_type": "video",
                "views": 200,
            },
        ]
    )
    analysis = pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "content_angle": "education",
                "hook_text": "3 mistakes",
                "hook_technique": "list_or_number",
                "creative_formula": "hook -> proof -> cta",
            },
            {
                "post_uid": "P2",
                "content_angle": "product_demo",
                "hook_text": "try this",
                "hook_technique": "bold_claim",
                "creative_formula": "hook -> demo -> cta",
            },
        ]
    )
    sequence = pd.DataFrame(
        [
            {"post_uid": "P1", "position": 1, "role": "hook", "primary_text": "3 mistakes"},
            {"post_uid": "P1", "position": 2, "role": "proof", "primary_text": "proof"},
        ]
    )
    performance = pd.DataFrame(
        [
            {"post_uid": "P1", "views_percentile_account": 0.8},
            {"post_uid": "P2", "views_percentile_account": 0.9},
        ]
    )
    families = pd.DataFrame(
        [
            {
                "family_id": "F1",
                "operator_id": "OP1",
                "member_count": 2,
                "accounts_count": 2,
                "cross_account": True,
                "core_angle": "education",
                "core_hook_text": "3 mistakes",
            }
        ]
    )
    members = pd.DataFrame(
        [
            {"family_id": "F1", "post_uid": "P1", "account_id": "A", "account": "alpha"},
            {"family_id": "F1", "post_uid": "P2", "account_id": "B", "account": "beta"},
        ]
    )
    propagation = pd.DataFrame(
        [
            {
                "family_id": "F1",
                "origin_account_id": "A",
                "origin_account": "alpha",
                "target_account_id": "B",
                "target_account": "beta",
                "target_first_post_uid": "P2",
                "delay_from_family_origin_days": 31.0,
            }
        ]
    )
    patterns = pd.DataFrame(
        [
            {
                "pattern_id": "PAT1",
                "pattern_type": "family_reuse_baseline",
                "title": "Reuse baseline",
                "observation": "Families repeat.",
                "sample_size": 10,
                "evidence_strength": "medium",
                "metrics_json": json.dumps({"cross_account_family_rate": 0.5}),
                "counter_evidence_json": json.dumps({"singletons": 5}),
                "causal_claim": False,
            }
        ]
    )
    pattern_links = pd.DataFrame(
        [
            {
                "pattern_id": "PAT1",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
                "link_role": "support",
            }
        ]
    )
    strategies = pd.DataFrame(
        [
            {
                "hypothesis_id": "STR1",
                "hypothesis_type": "iterative_reuse_model",
                "scope_type": "operator",
                "scope_id": "OP1",
                "operator_id": "OP1",
                "title": "Iterative reuse",
                "claim": "Operator likely reuses families.",
                "confidence_score": 0.82,
                "confidence_band": "high",
                "promotion_readiness": "review",
                "status": "hypothesis",
                "causal_claim": False,
                "evidence_summary_json": json.dumps({"multi_post_family_rate": 0.7}),
                "counter_evidence_json": json.dumps({}),
                "alternative_explanations_json": json.dumps(["Could be recycling."]),
            }
        ]
    )
    strategy_pattern_links = pd.DataFrame(
        [
            {
                "hypothesis_id": "STR1",
                "pattern_id": "PAT1",
                "relation": "support",
            }
        ]
    )
    strategy_evidence_links = pd.DataFrame(
        [
            {
                "hypothesis_id": "STR1",
                "pattern_id": "PAT1",
                "relation": "support",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
                "link_role": "support",
            }
        ]
    )
    knowledge = pd.DataFrame(
        [
            {
                "knowledge_id": "KSTR1",
                "knowledge_type": "strategy",
                "subtype": "iterative_reuse_model",
                "scope_type": "operator",
                "scope_id": "OP1",
                "operator_id": "OP1",
                "title": "Reuse families",
                "statement": "Use family-level iteration.",
                "actionable_guidance": "Keep family lineage.",
                "confidence_score": 0.82,
                "confidence_band": "high",
                "knowledge_status": "promoted",
                "source_type": "hypothesis",
                "source_ids_json": json.dumps(["STR1"]),
                "source_pattern_ids_json": json.dumps(["PAT1"]),
                "source_family_ids_json": json.dumps([]),
                "review_source_type": "hypothesis",
                "review_source_id": "STR1",
                "payload_json": json.dumps({"mode": "family"}),
                "exceptions_json": json.dumps(["Operator specific."]),
                "counter_evidence_json": json.dumps({}),
            },
            {
                "knowledge_id": "KLES1",
                "knowledge_type": "lesson",
                "subtype": "cadence",
                "scope_type": "operator",
                "scope_id": "OP1",
                "operator_id": "OP1",
                "title": "Cadence lesson",
                "statement": "Cadence may vary.",
                "confidence_score": 0.6,
                "confidence_band": "medium",
                "knowledge_status": "review_candidate",
                "source_type": "hypothesis",
                "source_ids_json": json.dumps(["STR2"]),
                "source_pattern_ids_json": json.dumps([]),
                "source_family_ids_json": json.dumps([]),
                "review_source_type": "hypothesis",
                "review_source_id": "STR2",
                "payload_json": "{}",
                "exceptions_json": "[]",
                "counter_evidence_json": "{}",
            },
        ]
    )
    knowledge_sources = pd.DataFrame(
        [
            {
                "knowledge_id": "KSTR1",
                "knowledge_type": "strategy",
                "source_type": "hypothesis",
                "source_id": "STR1",
                "relation": "derived_from",
            }
        ]
    )
    knowledge_evidence = pd.DataFrame(
        [
            {
                "knowledge_id": "KSTR1",
                "knowledge_type": "strategy",
                "source_type": "hypothesis",
                "source_id": "STR1",
                "pattern_id": "PAT1",
                "relation": "support",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
                "link_role": "support",
            }
        ]
    )
    windows = pd.DataFrame(
        [
            {
                "scope_type": "operator",
                "scope_id": "OP1",
                "period_id": "2026-01",
                "window_start_local": "2026-01-01",
                "posts": 1,
                "top_content_angle": "education",
                "product_rate": 0.0,
                "cta_rate": 0.0,
            },
            {
                "scope_type": "operator",
                "scope_id": "OP1",
                "period_id": "2026-02",
                "window_start_local": "2026-02-01",
                "posts": 1,
                "top_content_angle": "product_demo",
                "product_rate": 1.0,
                "cta_rate": 1.0,
            },
        ]
    )
    changes = pd.DataFrame(
        [
            {
                "scope_type": "operator",
                "scope_id": "OP1",
                "previous_period_id": "2026-01",
                "current_period_id": "2026-02",
                "is_change_point": True,
                "change_score": 0.6,
                "changed_dimensions_json": json.dumps(["content_angle"]),
            }
        ]
    )
    baselines = pd.DataFrame(
        [{"account_id": "A", "median_views": 100}, {"account_id": "B", "median_views": 200}]
    )
    cadence = pd.DataFrame(
        [{"account_id": "A", "median_gap_hours": 6.0}, {"account_id": "B", "median_gap_hours": 12.0}]
    )
    roles = pd.DataFrame(
        [
            {
                "account_id": "A",
                "originator_signal": 0.8,
                "receiver_signal": 0.1,
                "cross_account_flow_observations": 5,
                "descriptive_profile": "originator_leaning",
                "evidence_strength": "medium",
            },
            {
                "account_id": "B",
                "originator_signal": 0.1,
                "receiver_signal": 0.8,
                "cross_account_flow_observations": 5,
                "descriptive_profile": "receiver_leaning",
                "evidence_strength": "medium",
            },
        ]
    )
    return {
        "operators": operators,
        "accounts": accounts,
        "posts": posts,
        "creative_analysis": analysis,
        "creative_sequence": sequence,
        "performance": performance,
        "account_baselines": baselines,
        "account_cadence": cadence,
        "role_evidence": roles,
        "strategy_windows": windows,
        "strategy_changes": changes,
        "families": families,
        "family_members": members,
        "propagation": propagation,
        "patterns": patterns,
        "pattern_evidence_links": pattern_links,
        "strategies": strategies,
        "strategy_pattern_links": strategy_pattern_links,
        "strategy_evidence_links": strategy_evidence_links,
        "knowledge": knowledge,
        "knowledge_source_links": knowledge_sources,
        "knowledge_evidence_links": knowledge_evidence,
    }


def test_workspace_payloads_keep_cross_layer_lineage() -> None:
    payloads = build_workspace_payloads(**_frames())

    assert payloads["overview.json"]["counts"]["posts"] == 2
    assert payloads["overview.json"]["counts"]["active_knowledge_items"] == 1

    family = payloads["families.json"]["families"][0]
    assert len(family["members"]) == 2
    assert family["propagation"][0]["target_first_post_uid"] == "P2"

    pattern = payloads["patterns.json"]["patterns"][0]
    assert pattern["metrics"]["cross_account_family_rate"] == 0.5
    assert pattern["evidence_links"][0]["post_uid"] == "P1"

    strategy = payloads["strategies.json"]["strategies"][0]
    assert strategy["pattern_links"][0]["pattern_id"] == "PAT1"
    assert strategy["evidence_links"][0]["family_id"] == "F1"

    knowledge = payloads["knowledge.json"]
    assert len(knowledge["active"]) == 1
    assert knowledge["knowledge"][0]["source_links"][0]["source_id"] == "STR1"

    post = payloads["evidence.json"]["posts"][0]
    assert post["creative"]["hook_text"] == "3 mistakes"
    assert post["performance"]["views_percentile_account"] == 0.8
    assert post["family"]["family_id"] == "F1"
    assert post["sequence"][0]["role"] == "hook"

    lab = payloads["lab.json"]
    brief = lab["research_brief"]
    assert brief["stats"]["repeated_families"] == 1
    assert brief["stats"]["cross_account_repeated_families"] == 1
    assert brief["stats"]["cross_account_share_of_repeated"] == 1.0

    network = lab["account_network"]
    assert len(network["nodes"]) == 2
    assert len(network["edges"]) == 1
    assert network["edges"][0]["events"] == 1
    assert network["edges"][0]["origin_account_id"] == "A"
    assert network["edges"][0]["target_account_id"] == "B"

    assert lab["review"]["pending_sources"] == 2


def test_write_workspace_copies_static_and_required_data(tmp_path: Path) -> None:
    report = write_intelligence_workspace(
        out_dir=tmp_path,
        sources={"test": "fixture"},
        **_frames(),
    )
    assert report["counts"]["posts"] == 2

    for name in STATIC_FILES:
        assert (tmp_path / name).is_file()
    for name in REQUIRED_DATA_FILES:
        assert (tmp_path / name).is_file()

    assert validate_intelligence_workspace(tmp_path) == []

    workspace = json.loads((tmp_path / "workspace.json").read_text(encoding="utf-8"))
    assert workspace["workspace_schema_version"] == "operator-intelligence-lab-v3"
    assert workspace["views"] == [
        "production", "assets", "results", "evidence",
    ]
    assert workspace["evidence_modes"] == [
        "brief", "families", "network", "intelligence", "advanced",
    ]
    assert (tmp_path / "lab.json").is_file()
    assert (tmp_path / "production.json").is_file()
    assert (tmp_path / "production-kit.zip").is_file()
    kit = json.loads((tmp_path / "production.json").read_text(encoding="utf-8"))
    assert kit["schema_version"] == "creator-production-kit-v1"
    assert kit["quality"]["ready_to_publish"] == 0
    assert kit["quality"]["post_evidence_links"] >= 1



def test_workspace_prefers_local_archived_media_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CREATIVE_RESEARCH_PROJECT_ROOT",
        str(tmp_path),
    )
    archive = tmp_path / "data/02_media/tiktok/alpha/1"
    archive.mkdir(parents=True)
    (archive / "cover.jpg").write_bytes(b"cover")

    video_dir = tmp_path / "data/03_video_media/beta/2"
    video_dir.mkdir(parents=True)
    (video_dir / "video.mp4").write_bytes(b"video")

    frames = _frames()
    frames["posts"].loc[
        frames["posts"]["post_uid"].eq("P2"),
        "source_media_path",
    ] = "data/03_video_media/beta/2"

    payloads = build_workspace_payloads(**frames)
    posts = {
        row["post_uid"]: row
        for row in payloads["evidence.json"]["posts"]
    }

    assert posts["P1"]["preview"]["thumbnail_url"] == (
        "/api/media/thumbnail/P1"
    )
    assert posts["P1"]["preview"]["thumbnail_source"] == (
        "local_archive"
    )
    assert posts["P2"]["preview"]["video_url"] == (
        "/api/media/video/P2"
    )
    assert posts["P2"]["preview"]["video_source"] == "local_archive"


def test_rejected_and_held_hypotheses_are_not_featured_as_findings() -> None:
    frames = _frames()
    selected = pd.DataFrame(
        [{
            "hypothesis_id": "STR2",
            "hypothesis_type": "selective_cross_account_reuse_model",
            "scope_type": "operator",
            "operator_id": "OP1",
            "scope_id": "OP1",
            "title": "Selective cross-account reuse",
            "claim": "Repeated concepts sometimes move across accounts.",
            "confidence_score": 0.9,
            "confidence_band": "high",
            "evidence_summary_json": '{"multi_post_families": 1}',
        }]
    )
    frames["strategies"] = pd.concat(
        [frames["strategies"], selected], ignore_index=True
    )
    frames["knowledge"].loc[
        frames["knowledge"]["knowledge_id"].eq("KLES1"),
        "knowledge_status",
    ] = "rejected"
    lab = build_workspace_payloads(**frames)["lab.json"]
    assert not any(
        x["hypothesis_id"] == "STR2"
        for x in lab["research_brief"]["key_findings"]
    )
    assert lab["research_brief"]["hero"]["hypothesis_id"] is None

    frames["knowledge"].loc[
        frames["knowledge"]["knowledge_id"].eq("KLES1"),
        "knowledge_status",
    ] = "approved"
    lab = build_workspace_payloads(**frames)["lab.json"]
    assert lab["research_brief"]["hero"]["hypothesis_id"] == "STR2"
    assert lab["research_brief"]["key_findings"][0]["trust_status"] == "approved"


def test_lab_projects_flow_lineage_without_changing_role_denominator() -> None:
    frames = _frames()
    frames["propagation"].loc[0, "family_origin_post_uid"] = "P1"
    frames["role_evidence"].loc[
        frames["role_evidence"]["account_id"].eq("A"),
        "cross_account_flow_observations",
    ] = 1
    frames["role_evidence"].loc[
        frames["role_evidence"]["account_id"].eq("B"),
        "cross_account_flow_observations",
    ] = 1
    payloads = build_workspace_payloads(**frames)
    nodes = {
        item["account_id"]: item
        for item in payloads["lab.json"]["account_network"]["nodes"]
    }
    assert nodes["A"]["role_lineage"]["origin_family_count"] == 1
    assert nodes["A"]["role_lineage"]["imported_family_count"] == 0
    assert nodes["B"]["role_lineage"]["imported_family_count"] == 1
    assert nodes["A"]["lineage_matches_summary"]
    assert nodes["B"]["lineage_matches_summary"]
    entry = nodes["B"]["role_lineage"]["imported_families"][0]["flows"][0]
    assert (entry["origin_post_uid"], entry["target_post_uid"]) == ("P1", "P2")


def test_review_history_preserves_held_sources_for_reinspection() -> None:
    frames = _frames()
    frames["knowledge"].loc[
        frames["knowledge"]["knowledge_id"].eq("KLES1"),
        "knowledge_status",
    ] = "hold"
    frames["knowledge"].loc[
        frames["knowledge"]["knowledge_id"].eq("KLES1"),
        "review_decision",
    ] = "hold"
    frames["knowledge"].loc[
        frames["knowledge"]["knowledge_id"].eq("KLES1"),
        "review_note",
    ] = "Evidence insufficient to promote cadence."
    review = build_workspace_payloads(**frames)["lab.json"]["review"]
    assert review["pending_sources"] == 1
    assert review["reviewed_sources"] == 1
    assert review["reviewed_items"][0]["review_source_id"] == "STR2"
    assert review["reviewed_items"][0]["existing_review_decision"] == "hold"



def test_research_intelligence_v3_materializes_without_manual_approvals() -> None:
    frames = _frames()
    frames["knowledge"].loc[:, "knowledge_status"] = "review_candidate"
    lab = build_workspace_payloads(**frames)["lab.json"]
    research = lab["research_intelligence"]
    assert research["schema_version"] == "research-intelligence-v1"
    assert research["no_human_truth_approval_required"] is True
    assert research["operator_id"] == "OP1"
    assert research["counts"]["observed"] >= 2
    assert research["counts"]["inferred"] >= 1
    assert research["counts"]["unknown"] >= 3
    assert len(research["experiment_candidates"]) == 5
    assert all(
        row["experiment_not_proven"] is True
        for row in research["experiment_candidates"]
    )
    assert research["family_quality"]["human_review_required"] is False



def test_v3_lab_rejects_stale_export_even_when_static_files_exist(
    tmp_path: Path,
) -> None:
    """A mixed/stale Lab must never silently render the retired review UI."""
    write_intelligence_workspace(
        out_dir=tmp_path, sources={"test": "fixture"}, **_frames()
    )
    manifest_path = tmp_path / "workspace.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspace_schema_version"] = "operator-intelligence-lab-v2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    issues = validate_intelligence_workspace(tmp_path)
    assert any("stale export" in issue for issue in issues)
    manifest["workspace_schema_version"] = "operator-intelligence-lab-v3"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    lab_path = tmp_path / "lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab.pop("research_intelligence")
    lab_path.write_text(json.dumps(lab), encoding="utf-8")
    issues = validate_intelligence_workspace(tmp_path)
    assert "lab.json: missing Research Intelligence v3" in issues



def test_rebuild_prunes_legacy_copilot_asset_and_buttons(tmp_path: Path) -> None:
    """An upgraded v2 export must not serve a leftover on-demand AI widget."""
    retired = tmp_path / "ai_ui.js"
    retired.write_text(
        'document.write("Investigate further with AI (optional)")',
        encoding="utf-8",
    )
    assert retired.exists()

    write_intelligence_workspace(
        out_dir=tmp_path, sources={"test": "fixture"}, **_frames()
    )
    assert not retired.exists()
    assert "ai_ui.js" not in STATIC_FILES
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    app = (tmp_path / "app.js").read_text(encoding="utf-8")
    research = (tmp_path / "research_ui.js").read_text(encoding="utf-8")
    combined = html + app + research

    assert "Investigate further with AI" not in combined
    assert "Explore playbook further with AI" not in combined
    assert "AI Research Copilot" not in combined
    assert "optionalAiButton" not in combined
    assert "launchOptionalAI" not in combined
    assert "data-deep-ai-" not in combined
    assert "/api/ai/status" not in combined
    assert "AI Research Copilot" not in html



def test_rebuild_preserves_previous_embedded_team_results_in_private_state(
    tmp_path: Path,
) -> None:
    from creative_research.operating_state import OperatingStore

    workspace=tmp_path / "data/07_exports/operator-intelligence"
    write_intelligence_workspace(
        out_dir=workspace,
        sources={"test":"fixture"},
        **_frames(),
    )
    kit_path=workspace / "production.json"
    old=json.loads(kit_path.read_text(encoding="utf-8"))
    old["own_experiment_outcomes"]=[{
        "recipe_id":old["recipes"][0]["recipe_id"],
        "account_slot":"PILOT-A",
        "views":200, "account_median_views":100,
        "published_url":"https://www.tiktok.com/@myteam/video/987",
        "notes":"Legacy team experiment not age-matched",
        "evidence_origin":"first_party_team_reported_not_scraped_operator",
    }]
    kit_path.write_text(json.dumps(old),encoding="utf-8")
    # Rebuild is not allowed to make the only record disappear.
    write_intelligence_workspace(
        out_dir=workspace,
        sources={"test":"regenerated"},
        **_frames(),
    )
    after=json.loads(kit_path.read_text(encoding="utf-8"))
    assert "own_experiment_outcomes" not in after
    store=OperatingStore(workspace)
    legacy=store.view()["legacy_results"]
    assert len(legacy)==1
    assert legacy[0]["views"]==200
    assert legacy[0]["not_causal_proof"] is True
    assert legacy[0]["migrated_from"]=="creator-production-kit-v1-json"
    write_intelligence_workspace(
        out_dir=workspace,
        sources={"test":"another rebuild"},
        **_frames(),
    )
    assert len(OperatingStore(workspace).view()["legacy_results"])==1
