"""Checkpointed Gemini family judgments with explicit budgets and retries."""

from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from google import genai
from google.genai import types

from creative_research.analysis.family_judgments import (
    JUDGE_SCHEMA_VERSION,
    PROMPT_VERSION,
    TRANSLATION_VERIFIER_PROMPT_VERSION,
    TRANSLATION_VERIFIER_SCHEMA_VERSION,
    FamilyPairJudgment,
    TranslationVerification,
    apply_translation_verification,
    build_translation_verifier_prompt,
    clean_evidence_value,
    compute_evidence_hash,
    family_pair_id,
    is_truthy,
    judgment_cache_key,
    parse_optional_number,
    translation_cache_key,
    translation_evidence_hash,
)
from creative_research.infrastructure.gemini import build_generation_config, is_retryable_api_error
from creative_research.infrastructure.logging import redact
from creative_research.infrastructure.storage import append_jsonl, read_jsonl


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row["cache_key"]): row
        for row in read_jsonl(path, missing_ok=True, tolerate_invalid=True)
        if row.get("status") == "ok" and row.get("cache_key")
    }


def _usage_metadata(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    def read(*names: str) -> int | None:
        for name in names:
            value = getattr(usage, name, None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    return {
        "input_tokens": read("prompt_token_count", "input_token_count"),
        "output_tokens": read("candidates_token_count", "output_token_count"),
        "total_tokens": read("total_token_count"),
    }


def _call_translation_verifier(
    client: genai.Client,
    *,
    model: str,
    prompt: str,
    max_output_tokens: int,
) -> tuple[TranslationVerification, dict[str, int | None]]:
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=build_generation_config(
            TranslationVerification,
            max_output_tokens=max_output_tokens,
            thinking_level=types.ThinkingLevel.MINIMAL,
        ),
    )
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, TranslationVerification):
        return parsed, _usage_metadata(response)

    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Empty Gemini translation-verifier response")
    return (
        TranslationVerification.model_validate_json(text),
        _usage_metadata(response),
    )


def verify_translation_judgments(
    frame: pd.DataFrame,
    *,
    model: str,
    cache_path: Path,
    max_output_tokens: int,
    max_calls: int,
    min_confidence: float,
    retries: int,
    retry_base_seconds: float,
    sleep_between: float,
    force: bool,
    client: genai.Client,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if frame.empty or "relationship" not in frame.columns:
        return frame, {
            "translation_verifier_candidates": 0,
            "translation_verifier_api_calls": 0,
            "translation_verifier_cache_hits": 0,
            "translation_verifier_failures": 0,
            "translation_verifier_actual_input_tokens": 0,
            "translation_verifier_actual_output_tokens": 0,
            "translation_verifier_actual_total_tokens": 0,
            "translation_verifier_final_counts": {},
        }

    cache = _load_cache(cache_path)
    records = frame.to_dict(orient="records")
    candidates = [
        index
        for index, row in enumerate(records)
        if str(row.get("relationship") or "") == "translation_adaptation"
    ]

    api_calls = 0
    api_attempts = 0
    cache_hits = 0
    failures = 0
    actual_input_tokens = 0
    actual_output_tokens = 0
    actual_total_tokens = 0

    for position, record_index in enumerate(candidates, start=1):
        row = records[record_index]
        pair_id = str(row["pair_id"])
        evidence_hash = translation_evidence_hash(row)
        cache_key = translation_cache_key(
            pair_id,
            evidence_hash,
            model,
        )
        cached = None if force else cache.get(cache_key)

        verification: TranslationVerification | None = None
        usage: dict[str, int | None] = {}
        source = "cache"
        if cached is not None:
            cache_hits += 1
            verification = TranslationVerification.model_validate(cached["judgment"])
            usage = cached.get("usage") or {}
        else:
            if api_attempts >= max_calls:
                continue  # Mark unreached below, but still reuse later cached verifications.
            source = "api"
            last_error: str | None = None
            for attempt in range(retries + 1):
                if api_attempts >= max_calls:
                    break
                api_attempts += 1
                try:
                    verification, usage = _call_translation_verifier(
                        client,
                        model=model,
                        prompt=build_translation_verifier_prompt(row),
                        max_output_tokens=max_output_tokens,
                    )
                    api_calls += 1
                    break
                except Exception as exc:
                    last_error = redact(f"{type(exc).__name__}: {exc}")
                    if not is_retryable_api_error(exc):
                        break
                    if attempt < retries and api_attempts < max_calls:
                        wait = retry_base_seconds * (2**attempt) + random.random()
                        time.sleep(wait)

            if verification is None:
                failures += 1
                failed = dict(row)
                failed["primary_decision"] = row.get("decision")
                failed["primary_relationship"] = row.get("relationship")
                failed["primary_confidence"] = row.get("confidence")
                failed["primary_reason"] = row.get("reason")
                failed["decision"] = "uncertain"
                failed["relationship"] = "uncertain"
                failed["reason"] = (
                    "Translation verifier failed; defer to deterministic family evidence."
                )
                failed["translation_verifier_source"] = "failed"
                failed["translation_verifier_error"] = last_error
                records[record_index] = failed
                continue

            append_jsonl(
                cache_path,
                {
                    "status": "ok",
                    "cache_key": cache_key,
                    "pair_id": pair_id,
                    "evidence_hash": evidence_hash,
                    "model": model,
                    "prompt_version": (TRANSLATION_VERIFIER_PROMPT_VERSION),
                    "judge_schema_version": (TRANSLATION_VERIFIER_SCHEMA_VERSION),
                    "judgment": verification.model_dump(),
                    "usage": usage,
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )

        updated = apply_translation_verification(
            row,
            verification,
            min_confidence=min_confidence,
        )
        updated["translation_verifier_source"] = source
        records[record_index] = updated

        if source == "api":
            input_used = parse_optional_number(usage.get("input_tokens"))
            output_used = parse_optional_number(usage.get("output_tokens"))
            total_used = parse_optional_number(usage.get("total_tokens"))
            if input_used is not None:
                actual_input_tokens += int(input_used)
            if output_used is not None:
                actual_output_tokens += int(output_used)
            if total_used is not None:
                actual_total_tokens += int(total_used)

        print(
            f"  [translation {position}/{len(candidates)}] "
            f"{pair_id} {verification.central_idea_equivalence} "
            f"conf={verification.confidence:.2f} source={source}",
            flush=True,
        )
        if source == "api" and sleep_between:
            time.sleep(sleep_between)

    for record_index in candidates:
        row = records[record_index]
        if row.get("translation_verifier_source") is not None:
            continue
        deferred = dict(row)
        deferred["primary_decision"] = row.get("decision")
        deferred["primary_relationship"] = row.get("relationship")
        deferred["primary_confidence"] = row.get("confidence")
        deferred["primary_reason"] = row.get("reason")
        deferred["decision"] = "uncertain"
        deferred["relationship"] = "uncertain"
        deferred["reason"] = (
            "Translation verifier was not reached before its call cap; "
            "defer to deterministic family evidence."
        )
        deferred["translation_verifier_source"] = "not_reached"
        records[record_index] = deferred

    verified = pd.DataFrame(records)
    final_counts = (
        verified.loc[
            verified["primary_relationship"].fillna("").eq("translation_adaptation")
            if "primary_relationship" in verified.columns
            else pd.Series(False, index=verified.index),
            "relationship",
        ]
        .value_counts()
        .to_dict()
        if not verified.empty
        else {}
    )
    report = {
        "translation_verifier_candidates": len(candidates),
        "translation_verifier_api_calls": api_calls,
        "translation_verifier_api_attempts": api_attempts,
        "translation_verifier_cache_hits": cache_hits,
        "translation_verifier_failures": failures,
        "translation_verifier_actual_input_tokens": actual_input_tokens,
        "translation_verifier_actual_output_tokens": actual_output_tokens,
        "translation_verifier_actual_total_tokens": actual_total_tokens,
        "translation_verifier_final_counts": final_counts,
        "translation_verifier_min_confidence": min_confidence,
    }
    return verified, report


def _call_judge(
    client: genai.Client,
    *,
    model: str,
    prompt: str,
    max_output_tokens: int,
) -> tuple[FamilyPairJudgment, dict[str, int | None]]:
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=build_generation_config(
            FamilyPairJudgment,
            max_output_tokens=max_output_tokens,
            thinking_level=types.ThinkingLevel.MINIMAL,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, FamilyPairJudgment):
        return parsed, _usage_metadata(response)

    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Empty Gemini response")
    return (
        FamilyPairJudgment.model_validate_json(text),
        _usage_metadata(response),
    )


def execute_judgments(
    selected: list[dict[str, Any]],
    evidence_lookup: dict[str, dict[str, Any]],
    *,
    model: str,
    cache_path: Path,
    max_output_tokens: int,
    max_estimated_input_tokens: int,
    max_api_calls: int,
    retries: int,
    retry_base_seconds: float,
    sleep_between: float,
    force: bool,
    client: genai.Client,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cache = _load_cache(cache_path)
    rows: list[dict[str, Any]] = []
    api_calls = 0
    cache_hits = 0
    failures = 0
    actual_input_tokens = 0
    actual_output_tokens = 0
    actual_total_tokens = 0
    cached_historical_input_tokens = 0
    cached_historical_output_tokens = 0
    usage_rows = 0
    api_attempts = 0
    budgeted_input_tokens = 0
    stopped_for_budget = False
    stopped_for_api_call_cap = False

    for index, candidate in enumerate(selected, start=1):
        left_uid = str(candidate["left_post_uid"])
        right_uid = str(candidate["right_post_uid"])
        left = evidence_lookup[left_uid]
        right = evidence_lookup[right_uid]
        evidence_hash = compute_evidence_hash(left_uid, right_uid, left, right)
        pair_id = family_pair_id(left_uid, right_uid)
        cache_key = judgment_cache_key(pair_id, evidence_hash, model)
        estimated_input = int(candidate["_estimated_input_tokens"])

        judgment: FamilyPairJudgment | None
        usage: dict[str, int | None]
        cached = None if force else cache.get(cache_key)
        if cached is not None:
            cache_hits += 1
            judgment = FamilyPairJudgment.model_validate(cached["judgment"])
            usage = cached.get("usage") or {}
            source = "cache"
        else:
            last_error: str | None = None
            judgment = None
            usage = {}
            candidate_stopped = False
            for attempt in range(retries + 1):
                if api_attempts >= max_api_calls:
                    stopped_for_api_call_cap = True
                    last_error = "API call cap reached"
                    candidate_stopped = True
                    break
                if budgeted_input_tokens + estimated_input > max_estimated_input_tokens:
                    stopped_for_budget = True
                    last_error = "Input token budget reached"
                    candidate_stopped = True
                    break
                api_attempts += 1
                # Failed calls can cost money; reserve estimates for every attempt.
                budgeted_input_tokens += estimated_input
                try:
                    judgment, usage = _call_judge(
                        client,
                        model=model,
                        prompt=str(candidate["_prompt"]),
                        max_output_tokens=max_output_tokens,
                    )
                    api_calls += 1
                    reported_input = parse_optional_number(usage.get("input_tokens"))
                    if reported_input is not None:
                        budgeted_input_tokens += int(reported_input) - estimated_input
                    break
                except Exception as exc:
                    last_error = redact(f"{type(exc).__name__}: {exc}")
                    if not is_retryable_api_error(exc):
                        print(
                            f"  non-retryable API error: {last_error}",
                            flush=True,
                        )
                        break
                    if attempt < retries and api_attempts < max_api_calls:
                        wait = retry_base_seconds * (2**attempt) + random.random()
                        print(
                            f"  retry {attempt + 1}/{retries}: {last_error}; sleep {wait:.1f}s",
                            flush=True,
                        )
                        time.sleep(wait)

            if judgment is None:
                if candidate_stopped:
                    print(
                        f"[{index}/{len(selected)}] STOPPED: {last_error}",
                        flush=True,
                    )
                    continue  # Budget caps block new calls, not free cache hits later in the plan.
                failures += 1
                print(
                    f"[{index}/{len(selected)}] FAILED {pair_id}: {last_error}",
                    flush=True,
                )
                continue

            source = "api"
            append_jsonl(
                cache_path,
                {
                    "status": "ok",
                    "cache_key": cache_key,
                    "pair_id": pair_id,
                    "left_post_uid": left_uid,
                    "right_post_uid": right_uid,
                    "evidence_hash": evidence_hash,
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "judge_schema_version": JUDGE_SCHEMA_VERSION,
                    "judgment": judgment.model_dump(),
                    "usage": usage,
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )

        if judgment is None:
            raise RuntimeError(f"Missing judgment for {pair_id}")
        input_used = parse_optional_number(usage.get("input_tokens"))
        output_used = parse_optional_number(usage.get("output_tokens"))
        total_used = parse_optional_number(usage.get("total_tokens"))
        if source == "api":
            if input_used is not None:
                actual_input_tokens += int(input_used)
                usage_rows += 1
            if output_used is not None:
                actual_output_tokens += int(output_used)
            if total_used is not None:
                actual_total_tokens += int(total_used)
        else:
            if input_used is not None:
                cached_historical_input_tokens += int(input_used)
            if output_used is not None:
                cached_historical_output_tokens += int(output_used)

        rows.append(
            {
                "judge_schema_version": JUDGE_SCHEMA_VERSION,
                "prompt_version": PROMPT_VERSION,
                "pair_id": pair_id,
                "left_post_uid": left_uid,
                "right_post_uid": right_uid,
                "candidate_reason": candidate["_candidate_reason"],
                "combined_score": parse_optional_number(candidate.get("combined_score")),
                "structure_score": parse_optional_number(candidate.get("structure_score")),
                "semantic_text_score": parse_optional_number(candidate.get("semantic_text_score")),
                "production_family_score": parse_optional_number(
                    candidate.get("production_family_score")
                ),
                "cross_language": is_truthy(candidate.get("cross_language")),
                "cross_account": is_truthy(candidate.get("cross_account")),
                "left_account": clean_evidence_value(candidate.get("left_account")),
                "right_account": clean_evidence_value(candidate.get("right_account")),
                "left_language": clean_evidence_value(candidate.get("left_language")),
                "right_language": clean_evidence_value(candidate.get("right_language")),
                "left_hook_text": clean_evidence_value(candidate.get("left_hook_text")),
                "right_hook_text": clean_evidence_value(candidate.get("right_hook_text")),
                "left_topic": clean_evidence_value(candidate.get("left_topic")),
                "right_topic": clean_evidence_value(candidate.get("right_topic")),
                "left_angle": clean_evidence_value(candidate.get("left_angle")),
                "right_angle": clean_evidence_value(candidate.get("right_angle")),
                "model": model,
                "evidence_hash": evidence_hash,
                "cache_key": cache_key,
                "judgment_source": source,
                "decision": judgment.decision,
                "relationship": judgment.relationship,
                "core_concept": judgment.core_concept,
                "preserved_dimensions_json": json.dumps(
                    judgment.preserved_dimensions,
                    ensure_ascii=False,
                ),
                "changed_dimensions_json": json.dumps(
                    judgment.changed_dimensions,
                    ensure_ascii=False,
                ),
                "evidence_json": json.dumps(judgment.evidence, ensure_ascii=False),
                "counter_evidence_json": json.dumps(
                    judgment.counter_evidence,
                    ensure_ascii=False,
                ),
                "confidence": float(judgment.confidence),
                "reason": judgment.reason,
                "estimated_input_tokens": estimated_input,
                "actual_input_tokens": (int(input_used) if input_used is not None else None),
                "actual_output_tokens": (int(output_used) if output_used is not None else None),
                "actual_total_tokens": (int(total_used) if total_used is not None else None),
            }
        )

        print(
            f"[{index}/{len(selected)}] {pair_id} "
            f"{judgment.decision} {judgment.relationship} "
            f"conf={judgment.confidence:.2f} source={source}",
            flush=True,
        )
        if source == "api" and sleep_between:
            time.sleep(sleep_between)

    frame = pd.DataFrame(rows)
    report = {
        "selected_pairs": len(selected),
        "judged_rows": len(frame),
        "api_calls": api_calls,
        "api_attempts": api_attempts,
        "budgeted_input_tokens": budgeted_input_tokens,
        "max_api_calls": max_api_calls,
        "cache_hits": cache_hits,
        "failures": failures,
        "stopped_for_budget": stopped_for_budget,
        "stopped_for_api_call_cap": stopped_for_api_call_cap,
        "actual_input_tokens": actual_input_tokens if usage_rows else None,
        "actual_output_tokens": actual_output_tokens if usage_rows else None,
        "actual_total_tokens": actual_total_tokens if usage_rows else None,
        "cached_historical_input_tokens": cached_historical_input_tokens,
        "cached_historical_output_tokens": cached_historical_output_tokens,
        "usage_rows": usage_rows,
        "decision_counts": (frame["decision"].value_counts().to_dict() if not frame.empty else {}),
        "relationship_counts": (
            frame["relationship"].value_counts().to_dict() if not frame.empty else {}
        ),
    }
    return frame, report
