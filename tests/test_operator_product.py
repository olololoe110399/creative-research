from __future__ import annotations

from copy import deepcopy

from creative_research.operator_product import (
    build_provisional_playbook,
    build_role_flow_index,
    strategy_role_lineage,
)
from creative_research.outcome_acceptance import audit_outcome


def _flow(family: str, target: str, target_post: str) -> dict:
    return {
        "family_id": family,
        "origin_account_id": "A",
        "origin_account": "alpha",
        "target_account_id": target,
        "target_account": target.lower(),
        "family_origin_post_uid": "P1",
        "target_first_post_uid": target_post,
        "delay_from_family_origin_days": 2,
        "target_first_seen": "2026-02-02T00:00:00Z",
        "preserved_dimensions_json": '["content_angle"]',
        "changed_dimensions_json": '["hook_text"]',
    }


def _strategies() -> list[dict]:
    return [
        {
            "hypothesis_id": "S1",
            "hypothesis_type": "operator_explore_propagate_model",
            "operator_id": "OP1",
            "confidence_score": 0.9,
            "claim": "Account A is origin leaning.",
            "evidence_summary": {"origin_accounts": ["A"], "receiver_accounts": ["B"]},
        },
        {
            "hypothesis_id": "S2",
            "hypothesis_type": "selective_cross_account_reuse_model",
            "operator_id": "OP1",
            "confidence_score": 0.8,
            "claim": "Reuse is selective.",
        },
        {
            "hypothesis_id": "S3",
            "hypothesis_type": "preserve_core_vary_execution",
            "operator_id": "OP1",
            "confidence_score": 0.6,
            "claim": "Preserve core and change executions.",
        },
        {
            "hypothesis_id": "FOREIGN",
            "hypothesis_type": "selective_cross_account_reuse_model",
            "operator_id": "OP2",
            "confidence_score": 1.0,
            "claim": "Different operator; must not leak into OP1.",
        },
    ]


def _knowledge(statuses: dict[str, str]) -> list[dict]:
    return [
        {
            "operator_id": "OP1",
            "knowledge_id": "K" + source,
            "review_source_type": "hypothesis",
            "review_source_id": source,
            "knowledge_type": "strategy",
            "knowledge_status": state,
        }
        for source, state in statuses.items()
    ]


def test_origin_counts_unique_family_not_outbound_edge_events() -> None:
    lines = build_role_flow_index([_flow("F1", "B", "P2"), _flow("F1", "C", "P3")])
    assert lines["A"]["origin_family_count"] == 1
    assert lines["A"]["imported_family_count"] == 0
    assert lines["A"]["total_family_observations"] == 1
    assert len(lines["A"]["origin_families"][0]["flows"]) == 2
    assert lines["B"]["imported_family_count"] == 1
    assert lines["C"]["imported_family_count"] == 1
    assert lines["A"]["origin_families"][0]["flows"][0]["preserved_dimensions"] == [
        "content_angle"
    ]
    duplicate = build_role_flow_index([
        _flow("F1", "B", "P2"),
        _flow("F1", "B", "P2"),
    ])
    assert len(duplicate["A"]["origin_families"][0]["flows"]) == 1


def test_account_and_operator_claims_resolve_to_post_pairs() -> None:
    lines = build_role_flow_index([_flow("F1", "B", "P2")])
    claim = {
        "hypothesis_type": "account_reuse_receiver",
        "account_id": "B",
    }
    detail = strategy_role_lineage(claim, lines)
    assert detail is not None
    assert detail["accounts"][0]["imported_families"][0]["flows"][0]["origin_post_uid"] == "P1"
    assert detail["accounts"][0]["imported_families"][0]["flows"][0]["target_post_uid"] == "P2"
    model = strategy_role_lineage(_strategies()[0], lines)
    assert {item["account_id"] for item in model["accounts"]} == {"A", "B"}
    assert strategy_role_lineage({"hypothesis_type": "temporal_strategy_shift"}, lines) is None


def test_playbook_separates_review_from_confidence_and_blocks_rejected() -> None:
    rows = _strategies()
    knowledge = _knowledge({"S1": "rejected", "S2": "approved", "S3": "hold"})
    result = build_provisional_playbook(rows, knowledge, operator_id="OP1")
    by_key = {step["key"]: step for step in result["steps"]}
    assert result["status"] == "research_draft"
    assert result["approved_source_steps"] == 1
    assert by_key["explore"]["trust_status"] == "rejected"
    assert by_key["explore"]["application_exercise"] is None
    assert by_key["distribute"]["observation"] is None
    assert by_key["select"]["source_hypothesis_id"] == "S2"
    assert by_key["select"]["trust_status"] == "approved"
    assert by_key["adapt"]["trust_status"] == "hold"
    assert by_key["adapt"]["application_exercise"] is None
    assert by_key["measure"]["trust_status"] == "validation_protocol"
    assert by_key["measure"]["not_an_operator_claim"] is True
    assert by_key["measure"]["source_hypothesis_id"] is None
    auto = build_provisional_playbook(rows, _knowledge({"S2": "promoted"}), operator_id="OP1")
    assert auto["steps"][1]["trust_status"] == "auto_promoted"
    assert auto["approved_source_steps"] == 0
    missing = build_provisional_playbook([rows[0]], [], operator_id="OP1")
    assert missing["steps"][2]["trust_status"] == "no_evidence"
    assert missing["steps"][2]["application_exercise"] is None


def _payloads() -> dict:
    flow = _flow("F1", "B", "P2")
    lines = build_role_flow_index([flow])
    source = {
        "hypothesis_id": "S1",
        "hypothesis_type": "operator_explore_propagate_model",
        "account_id": None,
        "operator_id": "OP1",
        "evidence_summary": {
            "origin_accounts": ["A"],
            "receiver_accounts": ["B"],
        },
    }
    source["flow_evidence"] = strategy_role_lineage(source, lines)
    knowledge = _knowledge({"S1": "review_candidate"})
    playbook = build_provisional_playbook([source], knowledge, operator_id="OP1")
    return {
        "lab": {
            "research_brief": {
                "operator": {"operator_id": "OP1"},
                "hero": {"hypothesis_id": "S1"},
                "stats": {
                    "posts": 2,
                    "families": 1,
                    "repeated_families": 1,
                    "cross_account_repeated_families": 1,
                },
            },
            "account_network": {
                "nodes": [
                    {
                        "account_id": acct,
                        "flow_observations": 1,
                        "lineage_matches_summary": True,
                        "role_lineage": lines[acct],
                    }
                    for acct in ["A", "B"]
                ]
            },
            "playbook": playbook,
        },
        "families": {
            "families": [
                {
                    "family_id": "F1",
                    "member_count": 2,
                    "cross_account": True,
                    "members": [{"post_uid": "P1"}, {"post_uid": "P2"}],
                }
            ]
        },
        "strategies": {"strategies": [source]},
        "knowledge": {"knowledge": knowledge, "active": []},
        "evidence": {
            "posts": [
                {"post_uid": "P1", "account_id": "A", "url": "https://example.test/1"},
                {"post_uid": "P2", "account_id": "B", "url": "https://example.test/2"},
            ]
        },
    }


def test_outcome_audit_passes_evidence_with_explicit_review_gap() -> None:
    report = audit_outcome(**_payloads())
    assert report["status"] == "conditional_pass"
    assert report["failures"] == []
    assert report["counts"]["flow_pairs"] == 2
    warning_codes = {row["code"] for row in report["warnings"]}
    assert "human_review_pending" in warning_codes
    assert "manual_usability_unverified" in warning_codes


def test_outcome_audit_fails_broken_links_or_unearned_trust() -> None:
    payloads = _payloads()
    broken = deepcopy(payloads)
    broken["lab"]["account_network"]["nodes"][0]["role_lineage"][
        "origin_families"
    ][0]["flows"][0]["origin_post_uid"] = "MISSING"
    assert "missing_flow_post" in {
        row["code"] for row in audit_outcome(**broken)["failures"]
    }
    denied = deepcopy(payloads)
    denied["lab"]["playbook"]["steps"][0]["trust_status"] = "approved"
    denied["lab"]["playbook"]["approved_source_steps"] = 1
    assert "unearned_review_status" in {
        row["code"] for row in audit_outcome(**denied)["failures"]
    }
    denied = deepcopy(payloads)
    denied["lab"]["playbook"]["steps"][0]["trust_status"] = "hold"
    denied["lab"]["playbook"]["steps"][0]["application_exercise"] = "Do this now."
    assert "blocked_guidance_leak" in {
        row["code"] for row in audit_outcome(**denied)["failures"]
    }


def test_outcome_audit_fails_mismatched_role_denominator() -> None:
    payloads = _payloads()
    payloads["lab"]["account_network"]["nodes"][0]["flow_observations"] = 2
    assert "role_denominator_mismatch" in {
        row["code"] for row in audit_outcome(**payloads)["failures"]
    }



def test_core_review_can_pass_without_approving_weak_adaptation() -> None:
    sources = _strategies()
    knowledge = _knowledge({"S1": "approved", "S2": "approved", "S3": "hold"})
    playbook = build_provisional_playbook(sources, knowledge, operator_id="OP1")
    assert playbook["status"] == "core_reviewed"
    assert playbook["approved_core_steps"] == 3
    assert playbook["approved_source_steps"] == 3
    assert playbook["steps"][2]["trust_status"] == "hold"

    payloads = _payloads()
    payloads["lab"]["playbook"] = playbook
    payloads["strategies"]["strategies"].extend(sources[1:3])
    knowledge.append({
        "operator_id": "OP1",
        "knowledge_id": "KPLAY",
        "knowledge_type": "playbook",
        "knowledge_status": "approved",
    })
    payloads["knowledge"]["knowledge"] = knowledge
    payloads["knowledge"]["active"] = [
        row for row in knowledge if row["knowledge_status"] == "approved"
    ]
    report = audit_outcome(**payloads)
    assert report["failures"] == []
    assert report["status"] == "ready_for_usability_test"
    assert "adaptation_not_reviewed" in {
        issue["code"] for issue in report["warnings"]
    }



def test_v3_research_is_ready_without_any_human_truth_approvals() -> None:
    payloads = _payloads()
    payloads["lab"]["research_intelligence"] = {
        "operator_id": "OP1",
        "no_human_truth_approval_required": True,
        "observed": [{"id": "count", "statement": "Two posts, one repeated family"}],
        "inferred": [{
            "id": "S1", "claim": "Observed explore / propagate asymmetry",
            "interpretation_not_internal_fact": True,
        }],
        "unknown": [{"id": "intent", "statement": "Internal test/scale remains unknown"}],
        "family_quality": {
            "counts": {"repeated_families_checked": 1, "semantic_uncertain": 0},
            "human_review_required": False,
        },
        "experiment_candidates": [{
            "key": "explore", "title": "Pilot a concept",
            "related_hypothesis_id": "S1",
            "experiment_not_proven": True,
        }],
    }
    report = audit_outcome(**payloads)
    assert report["status"] == "ready_for_usability_test"
    assert report["failures"] == []
    assert report["counts"]["research_observed"] == 1
    assert "human_review_pending" not in {
        row["code"] for row in report["warnings"]
    }
    assert "no_trusted_catalog_playbook" not in {
        row["code"] for row in report["warnings"]
    }


def test_v3_research_audit_detects_untraceable_inference_or_fake_success() -> None:
    payloads = _payloads()
    payloads["lab"]["research_intelligence"] = {
        "operator_id": "OP1",
        "no_human_truth_approval_required": True,
        "observed": [{"id": "coverage"}],
        "inferred": [{"id": "FAKE-STRATEGY"}],
        "unknown": [{"id": "internal-intent"}],
        "family_quality": {
            "counts": {"repeated_families_checked": 1},
            "human_review_required": False,
        },
        "experiment_candidates": [{
            "key": "explore", "related_hypothesis_id": "FAKE",
            "experiment_not_proven": False,
        }],
    }
    codes = {entry["code"] for entry in audit_outcome(**payloads)["failures"]}
    assert "orphan_inferred_claim" in codes
    assert "orphan_experiment_source" in codes
    assert "experiment_misrepresented_as_proven" in codes
