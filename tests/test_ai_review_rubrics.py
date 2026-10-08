"""Regression tests for family/strategy review-scope contamination.

In particular, mixed receiving-post views must NOT turn a plausible creative
identity review into an unrelated test-to-scale hypothesis review.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from creative_research.ai_research import (
    AIResearchAnswer, AIResearchService, LabCorpus, ResearchValidationError,
    validate_answer,
)
from test_ai_research import corpus_fixture, valid_answer, valid_family_answer


def six_member_family(tmp_path: Path) -> Path:
    workspace = corpus_fixture(tmp_path)
    family_path = workspace / "families.json"
    evidence_path = workspace / "evidence.json"
    family_data = json.loads(family_path.read_text(encoding="utf-8"))
    evidence_data = json.loads(evidence_path.read_text(encoding="utf-8"))
    family = family_data["families"][0]
    family["family_id"] = "FAM-39E15050D193"
    family["core_topic"] = "study schedules for different student types"
    family["core_angle"] = "study_method"
    family["core_hook_text"] = "Study schedules for different students"
    family["core_hook_formula"] = "Categorize student personas and tailor schedules"
    family["core_creative_formula"] = "Student schedules, then a productivity app reveal"
    family["core_sequence_roles_json"] = '["hook","body","body","product_reveal"]'
    family["anchor_cohesion_min"] = 0.78145
    family["anchor_cohesion_mean"] = 0.82566
    family["member_count"] = 6
    family["accounts_count"] = 6
    member_ids = [f"POST-{n}" for n in range(6)]
    accounts = ["smartnotetips", "estudio1252", "nickystudy12",
                "study.with.hana7", "ninin0015", "tips.with.helen"]
    views = [10000, 840, 175500, 182500, 545, 182]
    source_posts = evidence_data["posts"]
    family["members"] = []
    for i, (uid, acc, count) in enumerate(zip(member_ids, accounts, views)):
        family["members"].append({
            "post_uid": uid,
            "family_member_index": i + 1,
            "match_score_to_origin": 1.0 if i == 0 else 0.78 + i * .012,
            "match_anchor_gate": "origin" if i == 0 else (
                "strong_ai_verified_translation" if i in (1, 2, 3, 4)
                else "strong_same_language"
            ),
            "match_reason_json": json.dumps({
                "strongest_signals": ["shared categorized schedule structure"]
            }),
        })
        source_posts.append({
            "operator_id": "OP1", "post_uid": uid,
            "account_id": f"ACCOUNT-{i}", "account": acc,
            "url": f"https://example.test/{uid}",
            "content_type": "slideshow", "views": count,
            "created_at": f"2025-0{i+1}-02T00:00:00Z",
            "family": {"family_id": "FAM-39E15050D193"},
            "performance": {"views_percentile_account": (i + 1) / 7},
            "creative": {
                "topic": "study schedules for different student types",
                "content_angle": "study_method",
                "hook_text": (
                    "Horarios de estudio para diferentes estudiantes"
                    if i in (1, 2, 3, 4)
                    else "Study schedules for different students"
                ),
                "creative_formula": "Categorize student study schedules, reveal tool",
                "product_family": "feynman",
            },
            "sequence": [
                {
                    "position": 1, "role": "hook",
                    "primary_text": "Study schedules for different students",
                    "visual_type": "study_desk_photo",
                },
                {
                    "position": 2, "role": "body",
                    "primary_text": "Early-bird schedule",
                    "visual_type": "text_schedule",
                },
                {
                    "position": 3, "role": "product_reveal",
                    "primary_text": "Productivity app recommendation",
                    "visual_type": "app_demo",
                },
            ],
        })
    family["propagation"] = [
        {
            "operator_id": "OP1", "family_id": "FAM-39E15050D193",
            "family_origin_post_uid": member_ids[0],
            "target_first_post_uid": member_ids[i],
            "target_vs_origin_views_percentile_delta": -0.9 if i == 5 else 0.4,
            "target_outperformed_origin": i != 5,
        }
        for i in range(1, 6)
    ]
    family_path.write_text(json.dumps(family_data), encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence_data), encoding="utf-8")
    lab_path = workspace / "lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab["review"]["items"].append({
        "review_source_type": "family", "review_source_id": family["family_id"]
    })
    lab_path.write_text(json.dumps(lab), encoding="utf-8")
    return workspace


def six_member_identity_answer() -> dict:
    answer = valid_family_answer(
        decision="approve",
        reason=(
            "Each member retains categorized schedules and the app-reveal sequence;"
            " Spanish hooks translate the same student-type premise."
        ),
    )
    member_refs = [f"post:POST-{n}" for n in range(6)]
    answer["summary"] = (
        "Six slideshow executions share a categorized student schedule concept"
        " with a late productivity-app reveal across languages."
    )
    answer["family_assessment"]["checked_member_post_refs"] = member_refs
    answer["family_assessment"]["identity_support_post_refs"] = member_refs
    answer["family_assessment"]["core_concept"] = (
        "Categorized schedules for student personas with late productivity-app reveal"
    )
    answer["findings"] = [
        {
            "interpretation": "observed",
            "statement": "Six original posts retain the student-type schedule framework.",
            "evidence_refs": ["family:FAM-39E15050D193", *member_refs[:6]],
        }
    ]
    return answer


def test_six_member_identity_packet_never_uses_views_as_membership_evidence(
    tmp_path: Path,
) -> None:
    workspace = six_member_family(tmp_path)
    packet = LabCorpus(workspace).packet(
        "investigate", "family", "FAM-39E15050D193"
    )
    assert packet["request"]["review_basis"] == "creative_family_identity"
    assert packet["family_identity"]["member_count"] == 6
    assert not packet["family_identity"]["member_sample_truncated"]
    assert packet["family_identity"]["human_visual_media_review_required"]
    assert len(packet["family_identity"]["member_post_refs"]) == 6
    assert packet["selected_flows"] == []
    serialized = json.dumps(packet)
    assert "182500" not in serialized
    assert "views" in packet["family_identity"]["decision_must_ignore"]
    for entry in packet["source_registry"]:
        assert "views" not in entry["data"]
        assert "performance" not in entry["data"]
        assert "views_percentile_account" not in json.dumps(entry["data"])
    refs = {
        item["evidence_ref"] for item in packet["source_registry"]
    }
    assert all(f"post:POST-{i}" in refs for i in range(6))
    assert "family:FAM-39E15050D193" in refs
    post_data = next(
        row["data"] for row in packet["source_registry"]
        if row["evidence_ref"] == "post:POST-5"
    )
    assert post_data["slide_or_video_sequence"][0]["role"] == "hook"
    assert post_data["family_match"]["match_score_to_origin"] > .78
    assert post_data["creative"]["product_family"] == "feynman"


def test_six_members_can_suggest_family_identity_approve_despite_varied_views(
    tmp_path: Path,
) -> None:
    workspace = six_member_family(tmp_path)
    service = AIResearchService(
        workspace, enabled=True, generator=lambda _: six_member_identity_answer()
    )
    plan, meta = service.plan("investigate", "family", "FAM-39E15050D193")
    assert "CREATIVE FAMILY MEMBERSHIP ONLY" in plan["prompt"]
    assert meta["review_basis"] == "creative_family_identity"
    assert meta["visual_media_inspected_by_ai"] is False
    report = service.run("investigate", "family", "FAM-39E15050D193")
    assert report["answer"]["proposed_review"] == "approve"
    assert report["answer"]["family_assessment"]["visual_media_inspected"] is False
    assert report["answer"]["experiments"] == []
    assert report["ai_status"] == "proposal_only"


@pytest.mark.parametrize("off_target", [
    "Hold because the receiver only had 182 views.",
    "Hold because we cannot prove the test-to-scale workflow.",
    "Hold because cross-account scaling was not causal.",
    "Hold because receiving executions underperformed.",
])
def test_family_review_rejects_wrong_performance_or_scale_criteria(
    tmp_path: Path, off_target: str,
) -> None:
    workspace = six_member_family(tmp_path)
    candidate = six_member_identity_answer()
    candidate["proposed_review"] = "hold"
    candidate["review_rationale"] = off_target
    # Pydantic requires reason long enough, so use a realistic full sentence.
    candidate["review_rationale"] += " This is why I would not approve family membership."
    service = AIResearchService(
        workspace, enabled=True, generator=lambda _: candidate
    )
    with pytest.raises(
        ResearchValidationError,
        match="family_identity_misframed_as_strategy_or_performance",
    ):
        service.run("investigate", "family", "FAM-39E15050D193")


def test_family_review_requires_all_members_and_real_outlier_for_rejection(
    tmp_path: Path,
) -> None:
    workspace = six_member_family(tmp_path)
    candidate = six_member_identity_answer()
    candidate["family_assessment"]["checked_member_post_refs"].pop()
    candidate["family_assessment"]["identity_support_post_refs"].pop()
    with pytest.raises(ResearchValidationError, match="family_approval_requires_all_members"):
        AIResearchService(
            workspace, enabled=True, generator=lambda _: candidate
        ).run("investigate", "family", "FAM-39E15050D193")

    candidate = six_member_identity_answer()
    candidate["proposed_review"] = "reject"
    with pytest.raises(ResearchValidationError, match="family_reject_requires_specific_outlier"):
        AIResearchService(
            workspace, enabled=True, generator=lambda _: candidate
        ).run("investigate", "family", "FAM-39E15050D193")


def test_family_review_forbids_experiments_and_false_visual_claims(
    tmp_path: Path,
) -> None:
    workspace = six_member_family(tmp_path)
    candidate = six_member_identity_answer()
    candidate["experiments"] = valid_answer(mode="draft_playbook")["experiments"]
    candidate["experiments"][0]["evidence_refs"] = [
        "family:FAM-39E15050D193", "post:POST-0"
    ]
    with pytest.raises(ResearchValidationError, match="family_review_cannot_generate_experiments"):
        AIResearchService(
            workspace, enabled=True, generator=lambda _: candidate
        ).run("investigate", "family", "FAM-39E15050D193")
    candidate = six_member_identity_answer()
    candidate["family_assessment"]["visual_media_inspected"] = True
    with pytest.raises(ValueError, match="visual_media_inspected"):
        AIResearchAnswer.model_validate(candidate)


def test_experiment_thresholds_are_labeled_and_new_velocity_data_required() -> None:
    candidate = valid_answer(mode="draft_playbook")
    experiment = candidate["experiments"][0]
    experiment["success_metric"] = "Receiving view velocity must exceed 0.50 percentile."
    experiment["stop_or_recheck"] = "Stop if below 0.30 percentile after 72 hours."
    experiment.pop("threshold_origin")
    with pytest.raises(
        ResearchValidationError, match="invented_threshold_without_proposed_label"
    ):
        validate_answer(
            AIResearchAnswer.model_validate(candidate),
            allowed_refs={"family:F1", "post:P1", "post:P2"},
            mode="draft_playbook",
        )
    experiment["threshold_origin"] = "proposed_experiment"
    with pytest.raises(
        ResearchValidationError, match="unavailable_velocity_requires_new_tracking"
    ):
        validate_answer(
            AIResearchAnswer.model_validate(candidate),
            allowed_refs={"family:F1", "post:P1", "post:P2"},
            mode="draft_playbook",
        )
    experiment["measurement_plan"] = "new_tracking_required"
    validate_answer(
        AIResearchAnswer.model_validate(candidate),
        allowed_refs={"family:F1", "post:P1", "post:P2"},
        mode="draft_playbook",
    )
