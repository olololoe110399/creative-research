from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from creative_research.analysis.family_judgments import FamilyPairJudgment, TranslationVerification
from creative_research.vision import family_judging


def _judgment():
    return FamilyPairJudgment(
        decision="same_core_concept",
        relationship="translation_adaptation",
        confidence=0.95,
        reason="synthetic equivalent idea",
    )


def _verification():
    return TranslationVerification(
        central_idea_equivalence="equivalent",
        translation_type="direct_translation",
        confidence=0.95,
        reason="synthetic translation",
    )


def _candidates(count=2):
    return [
        {
            "left_post_uid": f"L{index}",
            "right_post_uid": f"R{index}",
            "_estimated_input_tokens": 20,
            "_prompt": "synthetic evidence only",
            "_candidate_reason": "cross_language",
            "cross_language": True,
        }
        for index in range(count)
    ]


def _execute(tmp_path, client, selected=None, **overrides):
    selected = _candidates() if selected is None else selected
    evidence = {
        record[key]: {"post_uid": record[key], "topic": "synthetic"}
        for record in selected
        for key in ("left_post_uid", "right_post_uid")
    }
    options = {
        "model": "synthetic-model",
        "cache_path": tmp_path / "judge.jsonl",
        "max_output_tokens": 256,
        "max_estimated_input_tokens": 1000,
        "max_api_calls": 5,
        "retries": 2,
        "retry_base_seconds": 0,
        "sleep_between": 0,
        "force": False,
        "client": client,
        **overrides,
    }
    return family_judging.execute_judgments(selected, evidence, **options)


def _verify(tmp_path, client, frame, **overrides):
    options = {
        "model": "synthetic-model",
        "cache_path": tmp_path / "translation.jsonl",
        "max_output_tokens": 256,
        "max_calls": 5,
        "min_confidence": 0.85,
        "retries": 2,
        "retry_base_seconds": 0,
        "sleep_between": 0,
        "force": False,
        "client": client,
        **overrides,
    }
    return family_judging.verify_translation_judgments(frame, **options)


def _response(model, parsed=True, usage=True):
    return SimpleNamespace(
        parsed=model if parsed else None,
        text=model.model_dump_json(),
        usage_metadata=(
            SimpleNamespace(
                prompt_token_count=100, candidates_token_count=10, total_token_count=110
            )
            if usage
            else None
        ),
    )


@pytest.mark.parametrize("parsed", [True, False])
def test_judgments_and_translation_reuse_evidence_keyed_cache_without_new_spend(tmp_path, parsed):
    client = MagicMock()
    client.models.generate_content.return_value = _response(_judgment(), parsed)
    frame, report = _execute(tmp_path, client)
    assert report["api_calls"] == 2 and report["actual_input_tokens"] == 200
    cached, report = _execute(tmp_path, client, max_api_calls=0)
    assert report["api_calls"] == 0 and report["cache_hits"] == 2
    assert report["cached_historical_input_tokens"] == 200
    assert cached["judgment_source"].tolist() == ["cache", "cache"]
    client.models.generate_content.return_value = _response(_verification(), parsed)
    verified, report = _verify(tmp_path, client, frame)
    assert report["translation_verifier_api_calls"] == 2
    cached, report = _verify(tmp_path, client, frame, max_calls=0)
    assert report["translation_verifier_cache_hits"] == 2
    assert cached["translation_verifier_source"].tolist() == ["cache", "cache"]
    assert verified["relationship"].tolist() == ["translation_adaptation"] * 2
    assert client.models.generate_content.call_count == 4


@pytest.mark.parametrize("transient", [True, False])
def test_judging_retry_policy_and_api_attempt_cap_are_enforced(tmp_path, monkeypatch, transient):
    client = MagicMock()
    client.models.generate_content.side_effect = (
        TimeoutError("temporary") if transient else ValueError("bad schema")
    )
    monkeypatch.setattr(family_judging.time, "sleep", lambda seconds: None)
    frame, report = _execute(tmp_path, client, retries=4, max_api_calls=2)
    assert frame.empty
    assert report["api_attempts"] == client.models.generate_content.call_count == 2
    # A cap defers the unfinished pair; schema errors are completed failed attempts.
    assert report["failures"] == (0 if transient else 2)
    assert report["stopped_for_api_call_cap"] is transient
    assert not (tmp_path / "judge.jsonl").exists()


def test_input_token_cap_applies_even_when_provider_omits_usage(tmp_path):
    client = MagicMock()
    client.models.generate_content.return_value = _response(_judgment(), usage=False)
    frame, report = _execute(tmp_path, client, max_estimated_input_tokens=20)
    assert len(frame) == 1 and client.models.generate_content.call_count == 1
    assert report["stopped_for_budget"] is True
    assert report["actual_input_tokens"] is None


def test_budget_exhaustion_does_not_prevent_free_cache_reuse(tmp_path):
    client = MagicMock()
    client.models.generate_content.return_value = _response(_judgment())
    _execute(tmp_path, client, selected=_candidates()[1:])
    frame, report = _execute(tmp_path, client, max_estimated_input_tokens=100)
    assert len(frame) == 2 and report["cache_hits"] == 1 and report["api_calls"] == 1


def test_translation_cap_marks_unreached_pairs_uncertain_and_preserves_primary_decision(tmp_path):
    client = MagicMock()
    client.models.generate_content.return_value = _response(_judgment())
    frame, _ = _execute(tmp_path, client)
    client.models.generate_content.return_value = _response(_verification())
    verified, report = _verify(tmp_path, client, frame, max_calls=1)
    assert report["translation_verifier_api_attempts"] == 1
    assert verified.iloc[1]["decision"] == "uncertain"
    assert verified.iloc[1]["primary_decision"] == "same_core_concept"
    assert verified.iloc[1]["translation_verifier_source"] == "not_reached"


def test_translation_failure_does_not_promote_unverified_adaptation(tmp_path):
    client = MagicMock()
    client.models.generate_content.return_value = _response(_judgment())
    frame, _ = _execute(tmp_path, client)
    client.models.generate_content.side_effect = ValueError("bad translation response")
    verified, report = _verify(tmp_path, client, frame)
    assert report["translation_verifier_failures"] == 2
    assert verified["decision"].tolist() == ["uncertain", "uncertain"]
    assert verified["translation_verifier_source"].tolist() == ["failed", "failed"]


def test_empty_translation_input_does_not_create_cache_or_call_provider(tmp_path):
    client = MagicMock()
    frame, report = _verify(tmp_path, client, pd.DataFrame())
    assert frame.empty and report["translation_verifier_candidates"] == 0
    client.models.generate_content.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_oversized_first_request_is_rejected_before_spend(tmp_path):
    client = MagicMock()
    frame, report = _execute(tmp_path, client, max_estimated_input_tokens=10)
    assert frame.empty and report["stopped_for_budget"] is True
    assert report["budgeted_input_tokens"] == 0
    client.models.generate_content.assert_not_called()


def test_failed_retry_reserves_token_estimate_and_stops_before_budget_overrun(
    tmp_path, monkeypatch
):
    client = MagicMock()
    client.models.generate_content.side_effect = TimeoutError("synthetic timeout")
    monkeypatch.setattr(family_judging.time, "sleep", lambda seconds: None)
    frame, report = _execute(tmp_path, client, max_estimated_input_tokens=20, retries=4)
    assert frame.empty and report["stopped_for_budget"] is True
    assert report["api_attempts"] == client.models.generate_content.call_count == 1
    assert report["budgeted_input_tokens"] == 20
