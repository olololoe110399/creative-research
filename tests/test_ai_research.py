"""Offline contracts for AI research: real evidence IDs, trust, budgets, and cache.

No network/model calls are made by these tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from creative_research.ai_research import (
    AIResearchService,
    LabCorpus,
    ResearchValidationError,
    validate_answer,
    AIResearchAnswer,
)


def corpus_fixture(root: Path) -> Path:
    workspace = root / "data/07_exports/operator-intelligence"
    workspace.mkdir(parents=True)
    operator = "OP1"
    posts = [
        {
            "operator_id": operator, "post_uid": uid, "account_id": account,
            "account": account, "url": f"https://example.test/{uid}",
            "views": views, "created_at": date,
            "creative": {"hook_text": hook, "topic": "study", "content_angle": "teaching"},
            "performance": {"views_percentile_account": percentile},
            "family": {"family_id": fam},
        }
        for uid, account, fam, views, percentile, date, hook in (
            ("P1", "A", "F1", 1000, .9, "2025-01-01", "10 tips"),
            ("P2", "B", "F1", 100, .1, "2025-01-04", "other hook"),
            ("P3", "A", "F2", 300, .3, "2025-02-01", "same idea"),
            ("P4", "B", "F2", 950, .95, "2025-02-04", "better idea"),
            ("P5", "A", "F3", 50, .08, "2025-03-01", "only once"),
        )
    ]
    families = []
    for uid, origins, target, percentile in (
        ("F1", ["P1", "P2"], "P2", -.8),
        ("F2", ["P3", "P4"], "P4", .65),
    ):
        families.append({
            "operator_id": operator, "family_id": uid, "member_count": 2,
            "cross_account": True, "accounts_count": 2,
            "family_origin_post_uid": origins[0],
            "core_topic": "Study tips", "core_angle": "teaching",
            "propagation": [{
                "operator_id": operator, "family_id": uid,
                "family_origin_post_uid": origins[0],
                "target_first_post_uid": target,
                "origin_account": "A", "target_account": "B",
                "delay_from_family_origin_days": 3,
                "origin_views_percentile_account": .9 if uid == "F1" else .3,
                "target_first_views_percentile_account": .1 if uid == "F1" else .95,
                "target_vs_origin_views_percentile_delta": percentile,
                "target_outperformed_origin": percentile > 0,
                "preserved_dimensions_json": '["core_topic"]',
                "changed_dimensions_json": '["hook_text"]',
            }],
        })
    families.append({
        "operator_id": operator, "family_id": "F3", "member_count": 1,
        "family_origin_post_uid": "P5", "cross_account": False,
        "propagation": [],
    })
    strategy = {
        "operator_id": operator, "hypothesis_id": "STR1",
        "hypothesis_type": "selective_cross_account_reuse_model",
        "scope_type": "operator", "scope_id": operator,
        "claim": "Most families are one-offs and repeats usually span accounts.",
        "confidence_score": .88,
        "evidence_summary": {"repeated_families": 2},
        "counter_evidence": {"one_off": 1},
        "alternative_explanations": ["Cross-posting."],
        "pattern_links": [{"pattern_id": "PAT1"}],
        "evidence_links": [{"family_id": "F1", "post_uid": "P1"}],
        "flow_evidence": {"accounts": []},
    }
    pattern = {
        "operator_id": operator, "pattern_id": "PAT1",
        "title": "Reuse rate", "observation": "Repeated families often cross accounts.",
        "support_rate": 1.0, "sample_size": 3,
        "counter_evidence": {"singletons": 1},
        "evidence_links": [{"family_id": "F2", "post_uid": "P4"}],
    }
    data = {
        "lab": {
            "research_brief": {
                "operator": {"operator_id": operator, "name": "Fixture"},
                "hero": {"hypothesis_id": "STR1"},
                "stats": {
                    "accounts": 2, "posts": 5, "families": 3,
                    "repeated_families": 2,
                    "cross_account_repeated_families": 2,
                    "repeated_family_rate": 2/3,
                    "cross_account_share_of_repeated": 1.0,
                    "propagation_events": 2,
                },
                "guardrails": [
                    {"title": "No scale proven", "detail": "Chronology is not causality."}
                ],
                "key_findings": [{"hypothesis_id": "STR1"}],
            },
            "review": {
                "items": [
                    {
                        "review_source_type": "hypothesis", "review_source_id": "STR1",
                    },
                    {
                        "review_source_type": "family", "review_source_id": "F1",
                    },
                ],
                "reviewed_items": [],
            },
            "playbook": {"status": "research_draft", "steps": []},
        },
        "strategies": {"strategies": [strategy]},
        "patterns": {"patterns": [pattern]},
        "families": {"families": families},
        "evidence": {"posts": posts},
        "knowledge": {
            "knowledge": [
                {
                    "operator_id": operator, "knowledge_id": "K1",
                    "knowledge_type": "strategy", "review_source_type": "hypothesis",
                    "review_source_id": "STR1", "source_ids_json": '["STR1"]',
                    "knowledge_status": "review_candidate",
                    "statement": "Pending human decision.",
                }
            ],
            "active": [],
        },
    }
    for name, value in data.items():
        (workspace / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
    return workspace


def valid_answer(*, mode: str = "investigate") -> dict:
    return {
        "summary": "Cross-account repeat behavior has positive and negative executions.",
        "proposed_review": "not_applicable" if mode in (
            "draft_playbook", "stress_test"
        ) else "hold",
        "review_rationale": "The operator's internal selection mechanism is not known.",
        "findings": [
            {
                "interpretation": "observed",
                "statement": "Two executions are linked in one creative family.",
                "evidence_refs": ["family:F1", "post:P1"],
            },
            {
                "interpretation": "counterexample",
                "statement": "Receiving execution of F1 underperformed relative to origin.",
                "evidence_refs": ["post:P2", "family:F1"],
            },
        ],
        "alternative_explanations": ["Cross-posting without scaling."],
        "missing_evidence": ["Need repeat performance snapshots."],
        "experiments": [{
            "action": "Pilot one creative family on another account with a changed hook.",
            "success_metric": "Receiver views relative to its account median.",
            "stop_or_recheck": "Reconsider after 5 executions, including losses.",
            "evidence_refs": ["post:P2", "family:F1"],
        }] if mode == "draft_playbook" else [],
    }


def test_retrieval_scopes_and_includes_winning_losing_and_singletons(tmp_path: Path) -> None:
    path = corpus_fixture(tmp_path)
    corpus = LabCorpus(path)
    packet = corpus.packet("investigate", "hypothesis", "STR1")
    refs = {item["evidence_ref"] for item in packet["source_registry"]}
    assert packet["population_stats"]["posts"] == 5
    assert packet["population_stats"]["families"] == 3
    assert {"post:P1", "post:P2", "post:P3", "post:P4",
            "family:F1", "family:F2", "pattern:PAT1"}.issubset(refs)
    assert packet["sampling"]["available_flow_pairs"] == 2
    assert {f["outperformed"] for f in packet["selected_flows"]} == {True, False}
    other = corpus.packet("draft_playbook", "operator", "OP1")
    assert any(
        row["evidence_ref"] == "family:F3" for row in other["source_registry"]
    )
    with pytest.raises(ResearchValidationError, match="unknown_review_source"):
        corpus.packet("investigate", "hypothesis", "NOT-REAL")
    with pytest.raises(ResearchValidationError, match="invalid_operator_scope"):
        corpus.packet("draft_playbook", "operator", "OP2")


def test_ai_plan_is_free_and_cached_validated_report_is_immutable(tmp_path: Path) -> None:
    path = corpus_fixture(tmp_path)
    attempts: list[str] = []
    def fake_model(prompt: str) -> dict:
        attempts.append(prompt)
        return valid_answer()
    service = AIResearchService(path, enabled=True, generator=fake_model, max_calls=1)
    _plan, meta = service.plan("investigate", "hypothesis", "STR1")
    assert meta["source_count"] > 4
    assert meta["estimated_input_tokens_upper_bound"] > 0
    assert service.call_count == 0
    one = service.run("investigate", "hypothesis", "STR1")
    assert one["ai_status"] == "proposal_only"
    assert one["cannot_write_human_review"]
    assert one["answer"]["proposed_review"] == "hold"
    assert len(attempts) == 1
    second = service.run("investigate", "hypothesis", "STR1")
    assert second["from_cache"] is True
    assert second["request_id"] == one["request_id"]
    assert service.call_count == 1
    assert service.load(one["request_id"])["snapshot_sha256"] == one["snapshot_sha256"]
    assert not (tmp_path / "config/knowledge_reviews.toml").exists()
    assert service.report_dir.is_dir()
    with pytest.raises(ResearchValidationError, match="ai_call_limit_reached"):
        service.run("challenge", "hypothesis", "STR1")


def test_hallucinated_source_and_untrusted_approval_fail_closed(tmp_path: Path) -> None:
    path = corpus_fixture(tmp_path)
    answer = valid_answer()
    answer["findings"][0]["evidence_refs"] = ["post:FAKE"]
    bad = AIResearchService(path, enabled=True, generator=lambda _: answer)
    with pytest.raises(ResearchValidationError, match="hallucinated_evidence_ref"):
        bad.run("investigate", "hypothesis", "STR1")
    assert not list(bad.report_dir.glob("*.json"))

    missing = valid_answer(mode="challenge")
    missing["findings"] = [missing["findings"][0]]
    missing["missing_evidence"] = []
    validate = AIResearchAnswer.model_validate(missing)
    with pytest.raises(ResearchValidationError, match="challenge_without_counter_or_gap"):
        validate_answer(
            validate,
            allowed_refs={"post:P1", "family:F1"},
            mode="challenge",
        )

    review = valid_answer()
    review["proposed_review"] = "not_applicable"
    with pytest.raises(ResearchValidationError, match="review_mode_needs_suggestion"):
        validate_answer(
            AIResearchAnswer.model_validate(review),
            allowed_refs={"post:P1", "post:P2", "family:F1"},
            mode="investigate",
        )


def test_ai_can_draft_playbook_but_cannot_promote_or_use_blocked_knowledge(
    tmp_path: Path,
) -> None:
    path = corpus_fixture(tmp_path)
    service = AIResearchService(
        path, enabled=True,
        generator=lambda _: valid_answer(mode="draft_playbook"),
    )
    proposed = service.run("draft_playbook", "operator", "OP1")
    assert proposed["ai_status"] == "proposal_only"
    assert proposed["answer"]["experiments"][0]["stop_or_recheck"]
    assert proposed["answer"]["proposed_review"] == "not_applicable"
    rejected = AIResearchAnswer.model_validate(valid_answer(mode="draft_playbook"))
    rejected.experiments[0].evidence_refs = ["knowledge:K1"]
    with pytest.raises(ResearchValidationError, match="blocked_knowledge_used_as_guidance"):
        validate_answer(
            rejected,
            allowed_refs={"knowledge:K1", "post:P1", "post:P2", "family:F1"},
            mode="draft_playbook",
            blocked_source_refs={"knowledge:K1"},
        )


def test_snapshot_hash_changes_when_evidence_or_review_changes(tmp_path: Path) -> None:
    path = corpus_fixture(tmp_path)
    service = AIResearchService(
        path, enabled=True, generator=lambda _: valid_answer(), max_calls=2,
    )
    first = service.run("investigate", "hypothesis", "STR1")
    location = path / "knowledge.json"
    raw = json.loads(location.read_text(encoding="utf-8"))
    raw["knowledge"][0]["knowledge_status"] = "hold"
    location.write_text(json.dumps(raw), encoding="utf-8")
    second = service.run("investigate", "hypothesis", "STR1")
    assert second["request_id"] != first["request_id"]
    assert second["snapshot_sha256"] != first["snapshot_sha256"]
    assert service.call_count == 2


def test_invalid_report_id_and_disabled_ai(tmp_path: Path) -> None:
    path = corpus_fixture(tmp_path)
    service = AIResearchService(path)
    with pytest.raises(ResearchValidationError, match="ai_research_disabled"):
        service.run("investigate", "hypothesis", "STR1")
    with pytest.raises(ResearchValidationError, match="invalid_report_id"):
        service.load("../../etc/passwd")
    with pytest.raises(ValueError, match="unsupported_ai_model"):
        AIResearchService(path, model="gemini-arbitrary-expensive-model")
    with pytest.raises(ValueError, match="invalid_ai_call_limit"):
        AIResearchService(path, max_calls=1000)



def test_saved_ai_history_is_readable_and_warns_on_stale_snapshot(
    tmp_path: Path,
) -> None:
    path = corpus_fixture(tmp_path)
    service = AIResearchService(path, enabled=True, generator=lambda _: valid_answer())
    record = service.run("investigate", "hypothesis", "STR1")
    metadata = service.history("hypothesis", "STR1")
    assert len(metadata) == 1
    assert metadata[0]["request_id"] == record["request_id"]
    assert service.load(record["request_id"])["snapshot_is_current"] is True
    assert service.history("family", "F1") == []
    with pytest.raises(ResearchValidationError, match="unknown_research_source"):
        service.history("hypothesis", "FORGED")

    raw_path = path / "knowledge.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["knowledge"][0]["knowledge_status"] = "rejected"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    old = service.load(record["request_id"])
    assert old["snapshot_is_current"] is False
    assert old["ai_status"] == "proposal_only"
