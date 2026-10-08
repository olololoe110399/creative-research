from __future__ import annotations

from creative_research.research_intelligence import (
    build_research_intelligence, family_diagnostics,
)


def _evidence():
    posts = [
        {"post_uid": uid, "account_id": account, "operator_id": "OP1"}
        for uid, account in (("P1", "A"), ("P2", "B"), ("P3", "C"))
    ]
    families = [
        {
            "family_id": "F1", "operator_id": "OP1",
            "member_count": 2, "accounts_count": 2,
            "cross_account": True, "core_topic": "study schedules",
            "core_angle": "education",
        },
        {"family_id": "F2", "operator_id": "OP1", "member_count": 1},
    ]
    members = [
        {"family_id": "F1", "post_uid": "P1",
         "match_score_to_origin": 1.0},
        {"family_id": "F1", "post_uid": "P2",
         "match_score_to_origin": 0.82,
         "match_anchor_gate": "strong_translation"},
        {"family_id": "F2", "post_uid": "P3",
         "match_score_to_origin": 1.0},
    ]
    analysis = [
        {"post_uid": "P1", "primary_language_code": "en",
         "topic": "study schedules", "content_angle": "education"},
        {"post_uid": "P2", "primary_language_code": "es",
         "topic": "study schedules", "content_angle": "education"},
        {"post_uid": "P3", "primary_language_code": "en",
         "topic": "work routines", "content_angle": "productivity"},
    ]
    return families, members, posts, analysis


def test_automated_multilingual_family_qa_does_not_require_human_approval() -> None:
    families, members, posts, analysis = _evidence()
    report = family_diagnostics(
        families=families, members=members,
        posts=posts, creative_analysis=analysis,
    )
    assert report["human_review_required"] is False
    assert report["counts"] == {
        "repeated_families_checked": 1,
        "multilingual_families": 1,
        "integrity_gaps": 0,
        "semantic_uncertain": 0,
        "structurally_consistent_candidates": 1,
    }
    item = report["items"][0]
    assert item["automated_state"] == "structurally_consistent_candidate"
    assert item["languages"] == ["en", "es"]
    assert item["no_human_approval_required"] is True


def test_family_semantic_conflicts_are_machine_flags_not_manual_truth_checks() -> None:
    families, members, posts, analysis = _evidence()
    analysis[1]["topic"] = "completely different concept"
    members[1]["match_score_to_origin"] = 0.12
    members[1]["match_anchor_gate"] = "unverified"
    result = family_diagnostics(
        families=families, members=members,
        posts=posts, creative_analysis=analysis,
    )
    flagged = result["items"][0]
    assert flagged["automated_state"] == "semantic_uncertain"
    assert "low_anchor_match" in flagged["flags"]
    assert "multilingual_identity_needs_independent_check" in flagged["flags"]
    assert flagged["no_human_approval_required"]


def test_family_with_orphan_or_incomplete_members_is_integrity_gap() -> None:
    families, members, posts, analysis = _evidence()
    members[1]["post_uid"] = "MISSING"
    result = family_diagnostics(
        families=families, members=members,
        posts=posts, creative_analysis=analysis,
    )
    flagged = result["items"][0]
    assert flagged["automated_state"] == "integrity_gap"
    assert "orphan_post_evidence" in flagged["flags"]


def test_research_product_separates_observed_inferred_unknown_with_no_approvals() -> None:
    families, members, posts, analysis = _evidence()
    strategies = [{
        "hypothesis_id": "STR1",
        "hypothesis_type": "selective_cross_account_reuse_model",
        "operator_id": "OP1",
        "title": "Selective reuse possible",
        "claim": "Some creative concepts appear on multiple accounts.",
        "confidence_score": 0.81,
        "counter_evidence_json": '{"singletons": 1}',
        "alternative_explanations_json": '["independent adaptation"]',
    }]
    playbook = [{
        "key": "select",
        "title": "Try reusing one concept",
        "source_hypothesis_id": "STR1",
        "application_exercise": "Try different hooks in a controlled pilot.",
        "verification_question": "Compare both account baselines.",
        "confidence_score": 0.81,
    }, {
        "key": "measure",
        "title": "Collect own outcome evidence",
        "source_hypothesis_id": None,
        "application_exercise": None,
        "verification_question": "What happened in your pilot?",
    }]
    result = build_research_intelligence(
        operator_id="OP1",
        stats={
            "accounts": 3, "posts": 3, "families": 2,
            "repeated_families": 1, "cross_account_repeated_families": 1,
            "propagation_events": 1,
        },
        strategies=strategies,
        families=families,
        members=members,
        posts=posts,
        creative_analysis=analysis,
        account_nodes=[],
        playbook_steps=playbook,
    )
    assert result["no_human_truth_approval_required"] is True
    assert result["counts"]["observed"] == 3
    assert result["counts"]["inferred"] == 1
    assert result["counts"]["unknown"] >= 3
    assert result["inferred"][0]["evidence_ref"] == "hypothesis:STR1"
    assert "not proof" in result["limits"][2].lower() or "confidence" in result["limits"][2].lower()
    assert result["experiment_candidates"][0]["basis"] == "inferred"
    assert result["experiment_candidates"][1]["basis"] == "method_only"
    assert all(row["experiment_not_proven"] for row in result["experiment_candidates"])
