#!/usr/bin/env python3
"""AI semantic adjudication for ambiguous creative-family candidate pairs.

The stage is deliberately narrow:
- it consumes deterministic calibration candidates;
- it never sees performance metrics;
- it never reruns Vision;
- it never mutates production families;
- it caches judgments by evidence hash + model + prompt/schema version;
- it enforces a hard API-call cap and output-token cap, plus conservative
  estimated input-token planning.

The output is an auditable semantic edge layer that family-v2 preview/production
can consume later.
"""
# Do not enable postponed annotations in this stage.
# The CLI dispatches stages through runpy with run_name="__main__"; postponed
# Literal annotations can then be resolved against the wrong __main__ module
# when google-genai asks Pydantic for response_schema JSON.
import argparse
import hashlib
import json
import math
import os
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from creative_research.stages.preview_families_v2 import classify_pair
from creative_research.validation import read_table

JUDGE_SCHEMA_VERSION = "family-ai-judge-v1"
PROMPT_VERSION = "family-ai-judge-prompt-v1"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

DEFAULT_MIN_COMBINED = 0.74
DEFAULT_CROSS_LANGUAGE_MIN_COMBINED = 0.68
DEFAULT_CROSS_LANGUAGE_MIN_STRUCTURE = 0.90
DEFAULT_MAX_AI_PAIRS = 1000
DEFAULT_MAX_API_CALLS = 1100
DEFAULT_MAX_INPUT_TOKENS_PER_PAIR = 1800
DEFAULT_MAX_ESTIMATED_INPUT_TOKENS = 900_000
DEFAULT_MAX_OUTPUT_TOKENS = 768

MODEL_PRICING_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
}

TEXT_FIELDS = (
    "content_type",
    "primary_language_code",
    "audience_segment",
    "niche",
    "topic",
    "content_angle",
    "value_type",
    "pain_point",
    "desired_outcome",
    "hook_text",
    "hook_technique",
    "hook_psychological_trigger",
    "hook_replicable_formula",
    "content_format",
    "video_format",
    "narrative_structure",
    "dominant_visual_type",
    "product_family",
    "product_placement_style",
    "cta_type",
    "creative_formula",
)


class FamilyPairJudgment(BaseModel):
    decision: Literal[
        "same_core_concept",
        "different_core_concept",
        "uncertain",
    ]
    relationship: Literal[
        "exact_reuse",
        "translation_adaptation",
        "paraphrase",
        "hook_variant",
        "execution_variant",
        "thematic_only",
        "unrelated",
        "uncertain",
    ]
    core_concept: str | None = None
    preserved_dimensions: list[str] = Field(default_factory=list)
    changed_dimensions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reason: str


def _clean(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, str):
        text = value.strip()
        if not text or text.casefold() in {"nan", "none", "<na>"}:
            return None
        return text
    return value


def _number(value: Any) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    value = _clean(value)
    if value is None:
        return False
    if isinstance(value, str):
        return value.casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def _clip(value: Any, limit: int = 260) -> Any:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    else:
        rendered = str(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[: max(0, limit - 1)].rstrip() + "…"


def _sequence_lookup(sequence: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if sequence is None or sequence.empty or "post_uid" not in sequence.columns:
        return {}
    work = sequence.copy()
    if "position" in work.columns:
        work["_position"] = pd.to_numeric(work["position"], errors="coerce")
        work = work.sort_values(
            ["post_uid", "_position"],
            kind="mergesort",
            na_position="last",
        )

    result: dict[str, dict[str, Any]] = {}
    for post_uid, group in work.groupby("post_uid", sort=False, dropna=True):
        rows = group.to_dict(orient="records")[:12]
        roles = [
            _clip(row.get("role"), 60)
            for row in rows
            if _clean(row.get("role")) is not None
        ]
        visual_types = [
            _clip(row.get("visual_type"), 60)
            for row in rows
            if _clean(row.get("visual_type")) is not None
        ]
        key_text = [
            _clip(
                row.get("primary_text")
                or row.get("overlay_text")
                or row.get("spoken_summary"),
                140,
            )
            for row in rows[:5]
            if _clean(
                row.get("primary_text")
                or row.get("overlay_text")
                or row.get("spoken_summary")
            )
            is not None
        ]
        visual_descriptions = [
            _clip(row.get("visual_description"), 140)
            for row in rows[:4]
            if _clean(row.get("visual_description")) is not None
        ]
        result[str(post_uid)] = {
            "roles": roles,
            "visual_types": visual_types,
            "key_text": key_text,
            "visual_descriptions": visual_descriptions,
        }
    return result


def build_evidence_lookup(
    analysis: pd.DataFrame,
    sequence: pd.DataFrame | None = None,
) -> dict[str, dict[str, Any]]:
    if "post_uid" not in analysis.columns:
        raise ValueError("creative_analysis table missing post_uid")

    sequences = _sequence_lookup(sequence)
    result: dict[str, dict[str, Any]] = {}
    for row in analysis.to_dict(orient="records"):
        post_uid = str(row["post_uid"])
        evidence = {
            field: _clip(row.get(field))
            for field in TEXT_FIELDS
            if _clean(row.get(field)) is not None
        }
        evidence["sequence"] = sequences.get(post_uid, {})
        result[post_uid] = evidence
    return result


def _pair_id(left_post_uid: str, right_post_uid: str) -> str:
    left, right = sorted((left_post_uid, right_post_uid))
    raw = f"{left}\0{right}".encode("utf-8")
    return "AIP-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def _evidence_hash(
    left_post_uid: str,
    right_post_uid: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> str:
    first_uid, second_uid = sorted((left_post_uid, right_post_uid))
    payload = {
        "left": left if left_post_uid == first_uid else right,
        "left_post_uid": first_uid,
        "right": right if right_post_uid == second_uid else left,
        "right_post_uid": second_uid,
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _cache_key(pair_id: str, evidence_hash: str, model: str) -> str:
    raw = (
        f"{pair_id}\0{evidence_hash}\0{model}\0"
        f"{PROMPT_VERSION}\0{JUDGE_SCHEMA_VERSION}"
    ).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def build_prompt(
    left_post_uid: str,
    right_post_uid: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> str:
    payload = {
        "post_a": {"post_uid": left_post_uid, **left},
        "post_b": {"post_uid": right_post_uid, **right},
    }
    evidence_json = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    return f"""
You are a semantic judge for creative-research evidence.

Decide whether these two posts are executions of the SAME CORE CREATIVE CONCEPT.

CORE RULE:
A broad shared category is NOT enough.
For example, two posts can both be "study_method" while having different promises,
problems, mechanisms, or narrative concepts. Those should be different_core_concept.

Count as same_core_concept when the underlying creative idea is materially preserved,
including cases such as direct reuse, translation/localization, paraphrase, hook rewrite
around the same promise/problem, or execution/format adaptation around the same concept.

Use only the supplied creative evidence. Do not infer performance, intent, ownership,
or causation. If evidence is insufficient or mixed, return uncertain.

Relationship labels:
- exact_reuse: materially same creative with minimal change
- translation_adaptation: same concept translated/localized across languages
- paraphrase: same concept rewritten with equivalent meaning
- hook_variant: same core body/promise with a changed hook framing
- execution_variant: same concept expressed in a different format/execution
- thematic_only: same broad topic/category but not the same creative concept
- unrelated: not meaningfully the same concept
- uncertain: evidence is insufficient

Be strict about thematic_only versus same_core_concept.
Keep the JSON compact:
- reason: one sentence, maximum 180 characters;
- preserved_dimensions: at most 3 short items;
- changed_dimensions: at most 3 short items;
- evidence: at most 3 short items;
- counter_evidence: at most 2 short items;
- core_concept: one short phrase.
Do not add prose outside the JSON.

CREATIVE EVIDENCE:
{evidence_json}
""".strip()


def estimate_tokens(text: str) -> int:
    """Conservative heuristic for multilingual prompts; not a tokenizer."""
    return max(1, math.ceil(len(text) / 3.2))


def select_candidate_pairs(
    pairs: pd.DataFrame,
    evidence_lookup: dict[str, dict[str, Any]],
    *,
    min_combined: float = DEFAULT_MIN_COMBINED,
    cross_language_min_combined: float = DEFAULT_CROSS_LANGUAGE_MIN_COMBINED,
    cross_language_min_structure: float = DEFAULT_CROSS_LANGUAGE_MIN_STRUCTURE,
    max_ai_pairs: int = DEFAULT_MAX_AI_PAIRS,
    max_input_tokens_per_pair: int = DEFAULT_MAX_INPUT_TOKENS_PER_PAIR,
    max_estimated_input_tokens: int = DEFAULT_MAX_ESTIMATED_INPUT_TOKENS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    required = {
        "left_post_uid",
        "right_post_uid",
        "combined_score",
        "structure_score",
    }
    missing = sorted(required - set(pairs.columns))
    if missing:
        raise ValueError(
            "family calibration pairs missing required columns: "
            + ", ".join(missing)
        )

    eligible: list[dict[str, Any]] = []
    missing_evidence = 0
    prompt_too_large = 0

    for row in pairs.to_dict(orient="records"):
        if _truthy(row.get("same_current_family")):
            continue

        combined = _number(row.get("combined_score"))
        structure = _number(row.get("structure_score"))
        if combined is None or structure is None:
            continue

        deterministic_gate = classify_pair(row)
        reason: str | None = None
        if deterministic_gate is not None:
            reason = f"preview_gate:{deterministic_gate}"
        elif combined >= min_combined:
            reason = "borderline_combined"
        elif (
            _truthy(row.get("cross_language"))
            and combined >= cross_language_min_combined
            and structure >= cross_language_min_structure
        ):
            reason = "cross_language_structural"
        if reason is None:
            continue

        left_uid = str(row["left_post_uid"])
        right_uid = str(row["right_post_uid"])
        left = evidence_lookup.get(left_uid)
        right = evidence_lookup.get(right_uid)
        if left is None or right is None:
            missing_evidence += 1
            continue

        prompt = build_prompt(left_uid, right_uid, left, right)
        estimated_input_tokens = estimate_tokens(prompt)
        if estimated_input_tokens > max_input_tokens_per_pair:
            prompt_too_large += 1
            continue

        eligible.append(
            {
                **row,
                "_candidate_reason": reason,
                "_prompt": prompt,
                "_estimated_input_tokens": estimated_input_tokens,
            }
        )

    def sort_key(row: dict[str, Any]) -> tuple[int, int, float, float, str, str]:
        reason = str(row["_candidate_reason"])
        gate_priority = 0 if reason.startswith("preview_gate:") else 1
        cross_priority = 0 if _truthy(row.get("cross_language")) else 1
        combined = _number(row.get("combined_score")) or 0.0
        structure = _number(row.get("structure_score")) or 0.0
        return (
            gate_priority,
            cross_priority,
            -combined,
            -structure,
            str(row["left_post_uid"]),
            str(row["right_post_uid"]),
        )

    eligible.sort(key=sort_key)

    selected: list[dict[str, Any]] = []
    estimated_total = 0
    for row in eligible:
        if len(selected) >= max_ai_pairs:
            break
        estimate = int(row["_estimated_input_tokens"])
        if estimated_total + estimate > max_estimated_input_tokens:
            break
        selected.append(row)
        estimated_total += estimate

    report = {
        "eligible_pairs": len(eligible),
        "selected_pairs": len(selected),
        "excluded_missing_evidence": missing_evidence,
        "excluded_prompt_too_large": prompt_too_large,
        "max_ai_pairs": max_ai_pairs,
        "max_input_tokens_per_pair": max_input_tokens_per_pair,
        "max_estimated_input_tokens": max_estimated_input_tokens,
        "estimated_input_tokens_selected": estimated_total,
        "selection_reason_counts": (
            pd.Series(
                [row["_candidate_reason"] for row in selected],
                dtype="object",
            )
            .value_counts()
            .to_dict()
            if selected
            else {}
        ),
    }
    return selected, report


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(row, dict)
                and row.get("status") == "ok"
                and row.get("cache_key")
            ):
                result[str(row["cache_key"])] = row
    return result


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


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


def _http_status_from_error(exc: Exception) -> int | None:
    for name in ("status_code", "code"):
        value = getattr(exc, name, None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass

    text = str(exc)
    for status in (400, 401, 403, 404, 408, 409, 429, 500, 502, 503, 504):
        if f"{status}" in text:
            return status
    return None


def _retryable_api_error(exc: Exception) -> bool:
    status = _http_status_from_error(exc)
    if status is None:
        return True
    if status in {408, 409, 429}:
        return True
    if status >= 500:
        return True
    return False


def _generation_config(types: Any, max_output_tokens: int) -> Any:
    base = {
        "response_mime_type": "application/json",
        "response_schema": FamilyPairJudgment,
        "max_output_tokens": max_output_tokens,
        "thinking_config": types.ThinkingConfig(
            thinking_level="minimal",
        ),
    }
    try:
        return types.GenerateContentConfig(
            **base,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
    except Exception:
        return types.GenerateContentConfig(**base)


def _call_judge(
    client: Any,
    types: Any,
    *,
    model: str,
    prompt: str,
    max_output_tokens: int,
) -> tuple[FamilyPairJudgment, dict[str, int | None]]:
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=_generation_config(types, max_output_tokens),
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


def _pricing(
    model: str,
    input_rate: float | None,
    output_rate: float | None,
) -> tuple[float | None, float | None, str]:
    known = MODEL_PRICING_USD_PER_MILLION.get(model)
    resolved_input = input_rate
    resolved_output = output_rate
    source = "cli"
    if resolved_input is None and known is not None:
        resolved_input = known[0]
        source = "static_model_estimate"
    if resolved_output is None and known is not None:
        resolved_output = known[1]
        source = "static_model_estimate"
    if resolved_input is None or resolved_output is None:
        source = "unavailable"
    return resolved_input, resolved_output, source


def _estimated_cost(
    input_tokens: int,
    output_tokens: int,
    input_rate: float | None,
    output_rate: float | None,
) -> float | None:
    if input_rate is None or output_rate is None:
        return None
    return float(
        input_tokens / 1_000_000 * input_rate
        + output_tokens / 1_000_000 * output_rate
    )


def build_plan(
    pairs: pd.DataFrame,
    analysis: pd.DataFrame,
    sequence: pd.DataFrame | None,
    *,
    model: str,
    min_combined: float = DEFAULT_MIN_COMBINED,
    cross_language_min_combined: float = DEFAULT_CROSS_LANGUAGE_MIN_COMBINED,
    cross_language_min_structure: float = DEFAULT_CROSS_LANGUAGE_MIN_STRUCTURE,
    max_ai_pairs: int = DEFAULT_MAX_AI_PAIRS,
    max_input_tokens_per_pair: int = DEFAULT_MAX_INPUT_TOKENS_PER_PAIR,
    max_estimated_input_tokens: int = DEFAULT_MAX_ESTIMATED_INPUT_TOKENS,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    input_usd_per_million: float | None = None,
    output_usd_per_million: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    evidence_lookup = build_evidence_lookup(analysis, sequence)
    selected, selection_report = select_candidate_pairs(
        pairs,
        evidence_lookup,
        min_combined=min_combined,
        cross_language_min_combined=cross_language_min_combined,
        cross_language_min_structure=cross_language_min_structure,
        max_ai_pairs=max_ai_pairs,
        max_input_tokens_per_pair=max_input_tokens_per_pair,
        max_estimated_input_tokens=max_estimated_input_tokens,
    )
    estimated_output_tokens = len(selected) * max_output_tokens
    input_rate, output_rate, pricing_source = _pricing(
        model,
        input_usd_per_million,
        output_usd_per_million,
    )
    report = {
        **selection_report,
        "model": model,
        "judge_schema_version": JUDGE_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "min_combined": min_combined,
        "cross_language_min_combined": cross_language_min_combined,
        "cross_language_min_structure": cross_language_min_structure,
        "max_output_tokens_per_pair": max_output_tokens,
        "estimated_output_token_ceiling": estimated_output_tokens,
        "estimated_total_token_ceiling": (
            int(selection_report["estimated_input_tokens_selected"])
            + estimated_output_tokens
        ),
        "input_usd_per_million": input_rate,
        "output_usd_per_million": output_rate,
        "pricing_source": pricing_source,
        "estimated_cost_usd_ceiling": _estimated_cost(
            int(selection_report["estimated_input_tokens_selected"]),
            estimated_output_tokens,
            input_rate,
            output_rate,
        ),
        "pricing_note": (
            "Static model pricing is a convenience estimate verified against Google "
            "Gemini Developer API standard pricing on 2026-10-08 for "
            "gemini-3.5-flash-lite. The judge explicitly uses thinking_level=minimal; "
            "override price flags when needed."
        ),
    }
    return selected, report, evidence_lookup


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
    client: Any,
    types: Any,
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
    stopped_for_budget = False
    stopped_for_api_call_cap = False

    for index, candidate in enumerate(selected, start=1):
        left_uid = str(candidate["left_post_uid"])
        right_uid = str(candidate["right_post_uid"])
        left = evidence_lookup[left_uid]
        right = evidence_lookup[right_uid]
        evidence_hash = _evidence_hash(left_uid, right_uid, left, right)
        pair_id = _pair_id(left_uid, right_uid)
        cache_key = _cache_key(pair_id, evidence_hash, model)
        estimated_input = int(candidate["_estimated_input_tokens"])

        if (
            actual_input_tokens > 0
            and actual_input_tokens + estimated_input
            > max_estimated_input_tokens
        ):
            stopped_for_budget = True
            break

        cached = None if force else cache.get(cache_key)
        if cached is not None:
            cache_hits += 1
            judgment = FamilyPairJudgment.model_validate(cached["judgment"])
            usage = cached.get("usage") or {}
            source = "cache"
        else:
            last_error: str | None = None
            judgment = None
            usage: dict[str, int | None] = {}
            for attempt in range(retries + 1):
                if api_attempts >= max_api_calls:
                    stopped_for_api_call_cap = True
                    last_error = "API call cap reached"
                    break
                api_attempts += 1
                try:
                    judgment, usage = _call_judge(
                        client,
                        types,
                        model=model,
                        prompt=str(candidate["_prompt"]),
                        max_output_tokens=max_output_tokens,
                    )
                    api_calls += 1
                    break
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if not _retryable_api_error(exc):
                        print(
                            f"  non-retryable API error: {last_error}",
                            flush=True,
                        )
                        break
                    if attempt < retries and api_attempts < max_api_calls:
                        wait = retry_base_seconds * (2**attempt) + random.random()
                        print(
                            f"  retry {attempt + 1}/{retries}: "
                            f"{last_error}; sleep {wait:.1f}s",
                            flush=True,
                        )
                        time.sleep(wait)

            if judgment is None:
                if stopped_for_api_call_cap:
                    print(
                        f"[{index}/{len(selected)}] STOPPED: {last_error}",
                        flush=True,
                    )
                    break
                failures += 1
                print(
                    f"[{index}/{len(selected)}] FAILED "
                    f"{pair_id}: {last_error}",
                    flush=True,
                )
                continue

            source = "api"
            _append_jsonl(
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

        input_used = _number(usage.get("input_tokens"))
        output_used = _number(usage.get("output_tokens"))
        total_used = _number(usage.get("total_tokens"))
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
                "combined_score": _number(candidate.get("combined_score")),
                "structure_score": _number(candidate.get("structure_score")),
                "semantic_text_score": _number(candidate.get("semantic_text_score")),
                "production_family_score": _number(
                    candidate.get("production_family_score")
                ),
                "cross_language": _truthy(candidate.get("cross_language")),
                "cross_account": _truthy(candidate.get("cross_account")),
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
                "actual_input_tokens": (
                    int(input_used) if input_used is not None else None
                ),
                "actual_output_tokens": (
                    int(output_used) if output_used is not None else None
                ),
                "actual_total_tokens": (
                    int(total_used) if total_used is not None else None
                ),
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
        "decision_counts": (
            frame["decision"].value_counts().to_dict()
            if not frame.empty
            else {}
        ),
        "relationship_counts": (
            frame["relationship"].value_counts().to_dict()
            if not frame.empty
            else {}
        ),
    }
    return frame, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Judge ambiguous creative-family candidate pairs with Gemini using "
            "existing Vision evidence only. No performance metrics are sent."
        )
    )
    parser.add_argument(
        "--pairs",
        default=(
            "data/06_analytics/family_calibration/"
            "family_calibration_pairs.parquet"
        ),
    )
    parser.add_argument(
        "--analysis",
        default="data/05_master/creative_analysis.parquet",
    )
    parser.add_argument(
        "--sequence",
        default="data/05_master/creative_sequence.parquet",
    )
    parser.add_argument("--out", default="data/06_analytics/family_ai")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-combined", type=float, default=DEFAULT_MIN_COMBINED)
    parser.add_argument(
        "--cross-language-min-combined",
        type=float,
        default=DEFAULT_CROSS_LANGUAGE_MIN_COMBINED,
    )
    parser.add_argument(
        "--cross-language-min-structure",
        type=float,
        default=DEFAULT_CROSS_LANGUAGE_MIN_STRUCTURE,
    )
    parser.add_argument("--max-ai-pairs", type=int, default=DEFAULT_MAX_AI_PAIRS)
    parser.add_argument(
        "--max-api-calls",
        type=int,
        default=DEFAULT_MAX_API_CALLS,
        help="Hard cap across successful calls plus retry attempts.",
    )
    parser.add_argument(
        "--max-input-tokens-per-pair",
        type=int,
        default=DEFAULT_MAX_INPUT_TOKENS_PER_PAIR,
    )
    parser.add_argument(
        "--max-estimated-input-tokens",
        type=int,
        default=DEFAULT_MAX_ESTIMATED_INPUT_TOKENS,
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
    )
    parser.add_argument("--input-usd-per-million", type=float, default=None)
    parser.add_argument("--output-usd-per-million", type=float, default=None)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-base-seconds", type=float, default=1.5)
    parser.add_argument("--sleep-between", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pairs_path = Path(args.pairs).expanduser().resolve()
    analysis_path = Path(args.analysis).expanduser().resolve()
    sequence_path = Path(args.sequence).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = read_table(pairs_path)
    analysis = read_table(analysis_path)
    sequence = read_table(sequence_path) if sequence_path.exists() else None

    selected, plan, evidence_lookup = build_plan(
        pairs,
        analysis,
        sequence,
        model=args.model,
        min_combined=args.min_combined,
        cross_language_min_combined=args.cross_language_min_combined,
        cross_language_min_structure=args.cross_language_min_structure,
        max_ai_pairs=max(0, args.max_ai_pairs),
        max_input_tokens_per_pair=max(1, args.max_input_tokens_per_pair),
        max_estimated_input_tokens=max(1, args.max_estimated_input_tokens),
        max_output_tokens=max(1, args.max_output_tokens),
        input_usd_per_million=args.input_usd_per_million,
        output_usd_per_million=args.output_usd_per_million,
    )

    plan.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "pairs_source": str(pairs_path),
            "analysis_source": str(analysis_path),
            "sequence_source": (
                str(sequence_path) if sequence is not None else None
            ),
            "dry_run": args.dry_run,
            "max_api_calls": max(1, args.max_api_calls),
        }
    )

    print("Family AI judgment plan:")
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    plan_path = out_dir / "family_ai_plan.json"
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.dry_run:
        return

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Run with --dry-run to inspect "
            "pair/token/cost planning without an API key."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise SystemExit(
            "google-genai is required. Run uv sync --all-groups."
        ) from exc

    client = genai.Client(api_key=key)
    cache_path = out_dir / "family_ai_cache.jsonl"
    judgments, execution = execute_judgments(
        selected,
        evidence_lookup,
        model=args.model,
        cache_path=cache_path,
        max_output_tokens=max(1, args.max_output_tokens),
        max_estimated_input_tokens=max(1, args.max_estimated_input_tokens),
        max_api_calls=max(1, args.max_api_calls),
        retries=max(0, args.retries),
        retry_base_seconds=max(0.0, args.retry_base_seconds),
        sleep_between=max(0.0, args.sleep_between),
        force=args.force,
        client=client,
        types=types,
    )

    judgments_path = out_dir / "family_ai_judgments.parquet"
    jsonl_path = out_dir / "family_ai_judgments.jsonl"
    report_path = out_dir / "family_ai_report.json"

    judgments.to_parquet(judgments_path, index=False)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in judgments.to_dict(orient="records"):
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    input_rate = _number(plan.get("input_usd_per_million"))
    output_rate = _number(plan.get("output_usd_per_million"))
    actual_cost = None
    if (
        execution["actual_input_tokens"] is not None
        and execution["actual_output_tokens"] is not None
    ):
        actual_cost = _estimated_cost(
            int(execution["actual_input_tokens"]),
            int(execution["actual_output_tokens"]),
            input_rate,
            output_rate,
        )

    report = {
        **plan,
        **execution,
        "actual_cost_usd_estimate": actual_cost,
        "outputs": {
            "plan": str(plan_path),
            "judgments": str(judgments_path),
            "judgments_jsonl": str(jsonl_path),
            "cache": str(cache_path),
            "report": str(report_path),
        },
        "notes": [
            "No scrape was performed.",
            "No Vision creative re-analysis was performed.",
            "Performance metrics were not included in AI prompts.",
            "AI judgments are inferred evidence and do not mutate production families.",
            "Cache identity includes pair, evidence hash, model, prompt version, and judge schema version.",
        ],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
