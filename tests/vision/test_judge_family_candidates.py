from __future__ import annotations

import pandas as pd

from creative_research.analysis.family_judgments import (
    FamilyPairJudgment,
    TranslationVerification,
    apply_translation_verification,
    build_evidence_lookup,
    build_plan,
    build_prompt,
    build_translation_verifier_prompt,
    compute_evidence_hash,
    judgment_cache_key,
    merge_judgment_frames,
    select_candidate_pairs,
)
from creative_research.infrastructure.gemini import is_retryable_api_error


def _analysis() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "primary_language_code": "en",
                "audience_segment": "college_student",
                "niche": "student study",
                "topic": "study schedules for student types",
                "content_angle": "study_method",
                "value_type": "how_to",
                "pain_point": "poor study timing",
                "desired_outcome": "study at the right time",
                "hook_text": "Study schedules for different students",
                "hook_technique": "list_or_number",
                "hook_psychological_trigger": "personalization",
                "hook_replicable_formula": "study schedule for X student",
                "content_format": "listicle",
                "video_format": None,
                "narrative_structure": "hook -> segments -> CTA",
                "dominant_visual_type": "notes_or_document",
                "product_family": "none",
                "product_placement_style": "none",
                "cta_type": "save",
                "creative_formula": "segment students -> recommend schedule",
                "views": 999999,
                "likes": 9999,
            },
            {
                "post_uid": "P2",
                "primary_language_code": "es",
                "audience_segment": "college_student",
                "niche": "student study",
                "topic": "study schedules for student types",
                "content_angle": "study_method",
                "value_type": "how_to",
                "pain_point": "poor study timing",
                "desired_outcome": "study at the right time",
                "hook_text": "Horarios de estudio para diferentes estudiantes",
                "hook_technique": "list_or_number",
                "hook_psychological_trigger": "personalization",
                "hook_replicable_formula": "study schedule for X student",
                "content_format": "listicle",
                "video_format": None,
                "narrative_structure": "hook -> segments -> CTA",
                "dominant_visual_type": "notes_or_document",
                "product_family": "none",
                "product_placement_style": "none",
                "cta_type": "save",
                "creative_formula": "segment students -> recommend schedule",
                "views": 888888,
                "likes": 8888,
            },
            {
                "post_uid": "P3",
                "primary_language_code": "en",
                "topic": "unrelated morning routine",
                "content_angle": "productivity",
                "value_type": "relatable_story",
                "hook_text": "My 5am routine",
                "hook_technique": "pov",
                "creative_formula": "routine montage",
            },
        ]
    )


def _sequence() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "post_uid": "P1",
                "position": 1,
                "role": "hook",
                "visual_type": "notes_or_document",
                "primary_text": "Study schedules",
                "product_visible": False,
            },
            {
                "post_uid": "P2",
                "position": 1,
                "role": "hook",
                "visual_type": "notes_or_document",
                "primary_text": "Horarios de estudio",
                "product_visible": False,
            },
        ]
    )


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "left_post_uid": "P1",
                "right_post_uid": "P2",
                "combined_score": 0.82,
                "structure_score": 0.98,
                "semantic_text_score": 0.31,
                "production_family_score": 0.50,
                "cross_language": True,
                "cross_account": True,
                "same_current_family": False,
                "left_hook_text": "Study schedules for different students",
                "right_hook_text": "Horarios de estudio para diferentes estudiantes",
                "left_topic": "study schedules for student types",
                "right_topic": "study schedules for student types",
            },
            {
                "left_post_uid": "P1",
                "right_post_uid": "P3",
                "combined_score": 0.60,
                "structure_score": 0.60,
                "semantic_text_score": 0.20,
                "production_family_score": 0.30,
                "cross_language": False,
                "cross_account": False,
                "same_current_family": False,
                "left_hook_text": "Study schedules for different students",
                "right_hook_text": "My 5am routine",
                "left_topic": "study schedules for student types",
                "right_topic": "unrelated morning routine",
            },
        ]
    )


def test_prompt_uses_creative_evidence_and_excludes_performance() -> None:
    lookup = build_evidence_lookup(_analysis(), _sequence())
    prompt = build_prompt("P1", "P2", lookup["P1"], lookup["P2"])
    assert "Study schedules for different students" in prompt
    assert "Horarios de estudio" in prompt
    assert "999999" not in prompt
    assert '"views"' not in prompt
    assert '"likes"' not in prompt
    assert "shared app/product" in prompt
    assert "template_variant" in prompt
    assert "language difference alone is never enough" in prompt


def test_candidate_selection_prioritizes_preview_gate_and_budget() -> None:
    lookup = build_evidence_lookup(_analysis(), _sequence())
    selected, report = select_candidate_pairs(
        _pairs(),
        lookup,
        max_ai_pairs=1,
        max_input_tokens_per_pair=5000,
        max_estimated_input_tokens=5000,
    )
    assert len(selected) == 1
    assert selected[0]["left_post_uid"] == "P1"
    assert selected[0]["right_post_uid"] == "P2"
    assert selected[0]["_candidate_reason"].startswith("preview_gate:")
    assert report["selected_pairs"] == 1


def test_evidence_hash_and_cache_key_are_stable_across_pair_order() -> None:
    lookup = build_evidence_lookup(_analysis(), _sequence())
    h1 = compute_evidence_hash("P1", "P2", lookup["P1"], lookup["P2"])
    h2 = compute_evidence_hash("P2", "P1", lookup["P2"], lookup["P1"])
    assert h1 == h2
    k1 = judgment_cache_key("AIP-X", h1, "gemini-3.5-flash-lite")
    k2 = judgment_cache_key("AIP-X", h2, "gemini-3.5-flash-lite")
    assert k1 == k2


def test_build_plan_reports_token_and_cost_ceiling_without_api() -> None:
    selected, report, _ = build_plan(
        _pairs(),
        _analysis(),
        _sequence(),
        model="gemini-3.5-flash-lite",
        max_ai_pairs=10,
        max_input_tokens_per_pair=5000,
        max_estimated_input_tokens=5000,
        max_output_tokens=200,
    )
    assert len(selected) == 1
    assert report["estimated_input_tokens_selected"] > 0
    assert report["estimated_output_token_ceiling"] == 200
    assert report["estimated_cost_usd_ceiling"] is not None
    assert report["pricing_source"] == "static_model_estimate"


def test_family_pair_judgment_json_schema_is_fully_resolved() -> None:
    schema = FamilyPairJudgment.model_json_schema()
    properties = schema["properties"]
    assert "decision" in properties
    assert "relationship" in properties
    assert "confidence" in properties


def test_translation_verification_json_schema_is_fully_resolved() -> None:
    properties = TranslationVerification.model_json_schema()["properties"]
    assert properties["central_idea_equivalence"]["enum"] == [
        "equivalent",
        "different",
        "uncertain",
    ]
    assert "translation_type" in properties


class _FakeApiError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"{status_code} synthetic")
        self.status_code = status_code


def test_client_model_not_found_is_not_retryable() -> None:
    assert is_retryable_api_error(_FakeApiError(404)) is False
    assert is_retryable_api_error(_FakeApiError(400)) is False


def test_rate_limit_and_server_errors_are_retryable() -> None:
    assert is_retryable_api_error(_FakeApiError(429)) is True
    assert is_retryable_api_error(_FakeApiError(503)) is True


def test_prompt_requests_compact_json_output() -> None:
    lookup = build_evidence_lookup(_analysis(), _sequence())
    prompt = build_prompt("P1", "P2", lookup["P1"], lookup["P2"])
    assert "reason: one sentence" in prompt
    assert "preserved_dimensions: at most 3" in prompt
    assert "Do not add prose outside the JSON" in prompt


def test_analysis_lookup_does_not_include_performance_fields() -> None:
    lookup = build_evidence_lookup(_analysis(), _sequence())
    assert "views" not in lookup["P1"]
    assert "likes" not in lookup["P1"]


def test_merge_judgment_frames_preserves_unselected_existing_pairs() -> None:
    existing = pd.DataFrame(
        [
            {
                "pair_id": "AIP-1",
                "model": "gemini-3.5-flash-lite",
                "prompt_version": "family-ai-judge-prompt-v2",
                "judge_schema_version": "family-ai-judge-v2",
                "decision": "same_core_concept",
                "relationship": "translation_adaptation",
                "confidence": 0.95,
            },
            {
                "pair_id": "AIP-2",
                "model": "gemini-3.5-flash-lite",
                "prompt_version": "family-ai-judge-prompt-v2",
                "judge_schema_version": "family-ai-judge-v2",
                "decision": "different_core_concept",
                "relationship": "thematic_only",
                "confidence": 0.92,
            },
        ]
    )
    batch = pd.DataFrame(
        [
            {
                "pair_id": "AIP-3",
                "model": "gemini-3.5-flash-lite",
                "prompt_version": "family-ai-judge-prompt-v2",
                "judge_schema_version": "family-ai-judge-v2",
                "decision": "same_core_concept",
                "relationship": "paraphrase",
                "confidence": 0.90,
            }
        ]
    )
    merged, stats = merge_judgment_frames(
        existing,
        batch,
        model="gemini-3.5-flash-lite",
    )
    assert set(merged["pair_id"]) == {"AIP-1", "AIP-2", "AIP-3"}
    assert stats["existing_compatible_rows"] == 2
    assert stats["batch_judged_rows"] == 1
    assert stats["cumulative_judged_rows"] == 3


def test_merge_judgment_frames_replaces_same_pair_and_ignores_stale_versions() -> None:
    existing = pd.DataFrame(
        [
            {
                "pair_id": "AIP-1",
                "model": "gemini-3.5-flash-lite",
                "prompt_version": "family-ai-judge-prompt-v2",
                "judge_schema_version": "family-ai-judge-v2",
                "decision": "same_core_concept",
                "relationship": "paraphrase",
                "confidence": 0.70,
            },
            {
                "pair_id": "AIP-OLD",
                "model": "old-model",
                "prompt_version": "old-prompt",
                "judge_schema_version": "old-schema",
                "decision": "same_core_concept",
                "relationship": "exact_reuse",
                "confidence": 1.0,
            },
        ]
    )
    batch = pd.DataFrame(
        [
            {
                "pair_id": "AIP-1",
                "model": "gemini-3.5-flash-lite",
                "prompt_version": "family-ai-judge-prompt-v2",
                "judge_schema_version": "family-ai-judge-v2",
                "decision": "different_core_concept",
                "relationship": "thematic_only",
                "confidence": 0.96,
            }
        ]
    )
    merged, stats = merge_judgment_frames(
        existing,
        batch,
        model="gemini-3.5-flash-lite",
    )
    assert list(merged["pair_id"]) == ["AIP-1"]
    assert merged.iloc[0]["decision"] == "different_core_concept"
    assert stats["existing_incompatible_rows_ignored"] == 1
    assert stats["cumulative_judged_rows"] == 1


def test_judgment_schema_enforces_core_relationship_mapping() -> None:
    same = FamilyPairJudgment(
        decision="same_core_concept",
        relationship="translation_adaptation",
        core_concept="same study schedule concept",
        confidence=0.95,
        reason="Same central promise across languages.",
    )
    assert same.relationship == "translation_adaptation"

    different = FamilyPairJudgment(
        decision="different_core_concept",
        relationship="template_variant",
        core_concept=None,
        confidence=0.95,
        reason="Same app funnel but different central topics.",
    )
    assert different.relationship == "template_variant"


def test_judgment_schema_rejects_template_variant_as_same_core() -> None:
    import pytest

    with pytest.raises(ValueError):
        FamilyPairJudgment(
            decision="same_core_concept",
            relationship="template_variant",
            core_concept="shared template",
            confidence=0.95,
            reason="Same template only.",
        )


def test_prompt_explicitly_rejects_template_only_translation() -> None:
    lookup = build_evidence_lookup(_analysis(), _sequence())
    prompt = build_prompt("P1", "P2", lookup["P1"], lookup["P2"])
    assert "Electrolytes vs MRI Essentials" in prompt
    assert "same app funnel must be template_variant" in prompt
    assert "require semantic equivalence of the CENTRAL idea" in prompt


def test_translation_verifier_prompt_hides_execution_evidence() -> None:
    row = {
        "left_language": "en",
        "right_language": "es",
        "left_hook_text": "Will make parents proud",
        "right_hook_text": "Estudia hasta que estés emocionado por el examen.",
        "left_topic": "study motivation",
        "right_topic": "exam confidence",
        "product_family": "SECRET_PRODUCT_SHOULD_NOT_APPEAR",
        "creative_formula": "SECRET_TEMPLATE_SHOULD_NOT_APPEAR",
    }
    prompt = build_translation_verifier_prompt(row)
    assert "Will make parents proud" in prompt
    assert "Estudia hasta" in prompt
    assert "SECRET_PRODUCT_SHOULD_NOT_APPEAR" not in prompt
    assert "SECRET_TEMPLATE_SHOULD_NOT_APPEAR" not in prompt


def test_translation_verifier_rejects_different_central_idea() -> None:
    row = {
        "decision": "same_core_concept",
        "relationship": "translation_adaptation",
        "confidence": 0.95,
        "reason": "Primary judge called this a translation.",
        "core_concept": "study motivation",
    }
    verification = TranslationVerification(
        central_idea_equivalence="different",
        translation_type="not_translation",
        left_central_idea="Make parents proud through studying.",
        right_central_idea="Study until exams feel exciting.",
        confidence=0.96,
        reason="The central promises are different.",
    )
    result = apply_translation_verification(row, verification)
    assert result["primary_relationship"] == "translation_adaptation"
    assert result["decision"] == "different_core_concept"
    assert result["relationship"] == "template_variant"
    assert result["confidence"] == 0.96


def test_translation_verifier_keeps_real_translation() -> None:
    row = {
        "decision": "same_core_concept",
        "relationship": "translation_adaptation",
        "confidence": 0.98,
        "reason": "Primary translation.",
        "core_concept": "study schedules for different students",
    }
    verification = TranslationVerification(
        central_idea_equivalence="equivalent",
        translation_type="direct_translation",
        left_central_idea="Study schedules for different students.",
        right_central_idea="Study schedules for different students.",
        confidence=0.99,
        reason="The hooks express the same specific idea.",
    )
    result = apply_translation_verification(row, verification)
    assert result["decision"] == "same_core_concept"
    assert result["relationship"] == "translation_adaptation"
    assert result["confidence"] == 0.98


def test_translation_verifier_low_confidence_defers_to_deterministic() -> None:
    row = {
        "decision": "same_core_concept",
        "relationship": "translation_adaptation",
        "confidence": 0.95,
        "reason": "Primary translation.",
    }
    verification = TranslationVerification(
        central_idea_equivalence="equivalent",
        translation_type="localized_paraphrase",
        left_central_idea="Study smarter.",
        right_central_idea="Study more effectively.",
        confidence=0.70,
        reason="Possibly equivalent.",
    )
    result = apply_translation_verification(
        row,
        verification,
        min_confidence=0.85,
    )
    assert result["decision"] == "uncertain"
    assert result["relationship"] == "uncertain"


def test_translation_verifier_schema_rejects_inconsistent_mapping() -> None:
    import pytest

    with pytest.raises(ValueError):
        TranslationVerification(
            central_idea_equivalence="different",
            translation_type="direct_translation",
            confidence=0.95,
            reason="Contradictory output.",
        )
