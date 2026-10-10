"""Evidence-only family judging contracts, prompts, sampling and cost planning.

This module does not read files, create provider clients or perform API calls.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from creative_research.analysis.preview_families_v2 import classify_pair

JUDGE_SCHEMA_VERSION = "family-ai-judge-v2"


PROMPT_VERSION = "family-ai-judge-prompt-v2"


DEFAULT_MODEL = "gemini-3.5-flash-lite"


DEFAULT_MIN_COMBINED = 0.74


DEFAULT_CROSS_LANGUAGE_MIN_COMBINED = 0.68


DEFAULT_CROSS_LANGUAGE_MIN_STRUCTURE = 0.90


DEFAULT_MAX_AI_PAIRS = 1000


DEFAULT_MAX_API_CALLS = 1100


DEFAULT_MAX_INPUT_TOKENS_PER_PAIR = 1800


DEFAULT_MAX_ESTIMATED_INPUT_TOKENS = 900_000


DEFAULT_MAX_OUTPUT_TOKENS = 768


DEFAULT_TRANSLATION_VERIFIER_MAX_OUTPUT_TOKENS = 256


DEFAULT_MAX_TRANSLATION_VERIFIER_CALLS = 300


DEFAULT_TRANSLATION_VERIFIER_MIN_CONFIDENCE = 0.85


TRANSLATION_VERIFIER_SCHEMA_VERSION = "family-ai-translation-verifier-v1"


TRANSLATION_VERIFIER_PROMPT_VERSION = "family-ai-translation-verifier-prompt-v1"


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
        "template_variant",
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

    @model_validator(mode="after")
    def validate_decision_relationship(self) -> FamilyPairJudgment:
        same_core = {
            "exact_reuse",
            "translation_adaptation",
            "paraphrase",
            "hook_variant",
            "execution_variant",
        }
        different_core = {
            "template_variant",
            "thematic_only",
            "unrelated",
        }
        if self.decision == "same_core_concept" and self.relationship not in same_core:
            raise ValueError("same_core_concept requires an identity-preserving relationship")
        if self.decision == "different_core_concept" and self.relationship not in different_core:
            raise ValueError("different_core_concept requires template/thematic/unrelated")
        if self.decision == "uncertain" and self.relationship != "uncertain":
            raise ValueError("uncertain decision requires uncertain relationship")
        if self.relationship == "uncertain" and self.decision != "uncertain":
            raise ValueError("uncertain relationship requires uncertain decision")
        return self


class TranslationVerification(BaseModel):
    central_idea_equivalence: Literal[
        "equivalent",
        "different",
        "uncertain",
    ]
    translation_type: Literal[
        "direct_translation",
        "localized_paraphrase",
        "not_translation",
        "uncertain",
    ]
    left_central_idea: str | None = None
    right_central_idea: str | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str

    @model_validator(mode="after")
    def validate_translation_mapping(self) -> TranslationVerification:
        if self.central_idea_equivalence == "equivalent":
            if self.translation_type not in {
                "direct_translation",
                "localized_paraphrase",
            }:
                raise ValueError("equivalent central ideas require direct/localized translation")
        elif self.central_idea_equivalence == "different":
            if self.translation_type != "not_translation":
                raise ValueError("different central ideas require not_translation")
        elif self.translation_type != "uncertain":
            raise ValueError(
                "uncertain central idea equivalence requires uncertain translation type"
            )
        return self


def clean_evidence_value(value: Any) -> Any:
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


def parse_optional_number(value: Any) -> float | None:
    value = clean_evidence_value(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_truthy(value: Any) -> bool:
    value = clean_evidence_value(value)
    if value is None:
        return False
    if isinstance(value, str):
        return value.casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def _clip(value: Any, limit: int = 260) -> Any:
    value = clean_evidence_value(value)
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
            if clean_evidence_value(row.get("role")) is not None
        ]
        visual_types = [
            _clip(row.get("visual_type"), 60)
            for row in rows
            if clean_evidence_value(row.get("visual_type")) is not None
        ]
        key_text = [
            _clip(
                row.get("primary_text") or row.get("overlay_text") or row.get("spoken_summary"),
                140,
            )
            for row in rows[:5]
            if clean_evidence_value(
                row.get("primary_text") or row.get("overlay_text") or row.get("spoken_summary")
            )
            is not None
        ]
        visual_descriptions = [
            _clip(row.get("visual_description"), 140)
            for row in rows[:4]
            if clean_evidence_value(row.get("visual_description")) is not None
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
            if clean_evidence_value(row.get(field)) is not None
        }
        evidence["sequence"] = sequences.get(post_uid, {})
        result[post_uid] = evidence
    return result


def family_pair_id(left_post_uid: str, right_post_uid: str) -> str:
    left, right = sorted((left_post_uid, right_post_uid))
    raw = f"{left}\0{right}".encode()
    return "AIP-" + hashlib.sha1(raw).hexdigest()[:12].upper()


def compute_evidence_hash(
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


def judgment_cache_key(pair_id: str, evidence_hash: str, model: str) -> str:
    raw = (
        f"{pair_id}\0{evidence_hash}\0{model}\0{PROMPT_VERSION}\0{JUDGE_SCHEMA_VERSION}"
    ).encode()
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
You are a strict semantic identity judge for creative-research evidence.

Decide whether these two posts are executions of the SAME CORE CREATIVE CONCEPT.

IDENTITY TEST:
Temporarily ignore the shared app/product, CTA, visual style, listicle format,
sequence, product reveal, and creator niche. Ask:
"Would a human still describe both posts with the same specific one-sentence
creative idea, promise/problem, and central subject?"

If NO, they are NOT the same core concept even if their execution template is
nearly identical.

SAME CORE examples:
- direct reuse of the same post concept;
- a real translation/localization of the same specific hook/promise/topic;
- a paraphrase preserving the same specific idea;
- a new hook framing for the same body/promise/topic;
- a different visual execution of the same specific concept.

DIFFERENT CORE examples:
- Electrolytes vs MRI Essentials, despite identical medical-note/app format;
- lung sounds vs injection types, despite identical nursing template;
- "5 tiny habits" vs "become disgustingly educated", despite the same app funnel;
- two generic motivational hooks that both end with the same study app;
- different medical/study subjects that merely reuse the same listicle/product reveal.

Relationship labels:
- exact_reuse: materially the same creative with minimal change
- translation_adaptation: a genuine cross-language translation/localization of the
  same specific central hook/promise/topic; language difference alone is never enough
- paraphrase: same specific concept rewritten with equivalent meaning
- hook_variant: same specific body/promise/topic with only hook framing changed
- execution_variant: same specific concept, different visual/format execution
- template_variant: same reusable execution template/product funnel, but a different
  central topic, promise, problem, list subject, or medical/study subject
- thematic_only: same broad niche/category but not the same concept or close template
- unrelated: no meaningful concept/template relationship
- uncertain: evidence is insufficient

DECISION MAPPING IS STRICT:
- same_core_concept -> exact_reuse / translation_adaptation / paraphrase /
  hook_variant / execution_variant
- different_core_concept -> template_variant / thematic_only / unrelated
- uncertain -> uncertain

IMPORTANT:
Shared app/product, late product reveal, listicle structure, aesthetics, audience,
or sequence are supporting execution evidence only. They can justify template_variant,
but NEVER by themselves justify same_core_concept or translation_adaptation.

For translation_adaptation, require semantic equivalence of the CENTRAL idea.
Different hooks/topics with the same app funnel must be template_variant or
thematic_only, not translation_adaptation.

Use only supplied creative evidence. Do not infer performance, intent, ownership,
or causation.

Keep JSON compact:
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


def build_translation_verifier_prompt(row: dict[str, Any]) -> str:
    evidence = {
        "post_a": {
            "language": clean_evidence_value(row.get("left_language")),
            "hook_text": clean_evidence_value(row.get("left_hook_text")),
            "topic": clean_evidence_value(row.get("left_topic")),
        },
        "post_b": {
            "language": clean_evidence_value(row.get("right_language")),
            "hook_text": clean_evidence_value(row.get("right_hook_text")),
            "topic": clean_evidence_value(row.get("right_topic")),
        },
    }
    return f"""
You are a strict translation/localization verifier.

You see ONLY the central hook/topic evidence for two posts.
You do NOT see app/product, CTA, format, visuals, sequence, creator, or performance.

First independently normalize each post's central idea into one short English sentence.
Then decide whether the two central ideas are semantically equivalent enough to be
a genuine translation/localization of the same specific creative concept.

Equivalent means the same specific promise/problem/topic or a close localized paraphrase.
Different wording is fine. Different central subject, promise, problem, list theme,
motivation, medical topic, or study topic is NOT equivalent.

Examples of DIFFERENT:
- "Will make parents proud" vs "study until you're excited for the exam"
- "5 tiny habits that made me a better student" vs "5 things about studying I wish I knew"
- "enjoy med school, you'll be a doctor soon" vs "don't give up; imagine their faces"
- generic exam stress vs a specific exam-confidence feeling

Do not infer equivalence from shared niche or likely app funnel; you cannot see those
features and must judge only the central idea evidence below.

Return compact structured JSON only.

EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
""".strip()


def translation_evidence_hash(row: dict[str, Any]) -> str:
    payload = {
        "left_language": clean_evidence_value(row.get("left_language")),
        "right_language": clean_evidence_value(row.get("right_language")),
        "left_hook_text": clean_evidence_value(row.get("left_hook_text")),
        "right_hook_text": clean_evidence_value(row.get("right_hook_text")),
        "left_topic": clean_evidence_value(row.get("left_topic")),
        "right_topic": clean_evidence_value(row.get("right_topic")),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def translation_cache_key(
    pair_id: str,
    evidence_hash: str,
    model: str,
) -> str:
    raw = (
        f"{pair_id}\0{evidence_hash}\0{model}\0"
        f"{TRANSLATION_VERIFIER_PROMPT_VERSION}\0"
        f"{TRANSLATION_VERIFIER_SCHEMA_VERSION}"
    ).encode()
    return hashlib.sha1(raw).hexdigest()


def apply_translation_verification(
    row: dict[str, Any],
    verification: TranslationVerification,
    *,
    min_confidence: float = DEFAULT_TRANSLATION_VERIFIER_MIN_CONFIDENCE,
) -> dict[str, Any]:
    result = dict(row)
    result["primary_decision"] = row.get("decision")
    result["primary_relationship"] = row.get("relationship")
    result["primary_confidence"] = row.get("confidence")
    result["primary_reason"] = row.get("reason")
    result["translation_verifier_schema_version"] = TRANSLATION_VERIFIER_SCHEMA_VERSION
    result["translation_verifier_prompt_version"] = TRANSLATION_VERIFIER_PROMPT_VERSION
    result["translation_verifier_equivalence"] = verification.central_idea_equivalence
    result["translation_verifier_type"] = verification.translation_type
    result["translation_verifier_left_central_idea"] = verification.left_central_idea
    result["translation_verifier_right_central_idea"] = verification.right_central_idea
    result["translation_verifier_confidence"] = float(verification.confidence)
    result["translation_verifier_reason"] = verification.reason

    if verification.confidence < min_confidence:
        result["decision"] = "uncertain"
        result["relationship"] = "uncertain"
        result["reason"] = (
            "Translation verifier confidence below threshold; "
            "defer to deterministic family evidence."
        )
        result["confidence"] = float(verification.confidence)
        return result

    if verification.central_idea_equivalence == "equivalent":
        result["decision"] = "same_core_concept"
        result["relationship"] = "translation_adaptation"
        result["confidence"] = min(
            float(parse_optional_number(row.get("confidence")) or 0.0),
            float(verification.confidence),
        )
        result["reason"] = verification.reason
        return result

    if verification.central_idea_equivalence == "different":
        result["decision"] = "different_core_concept"
        result["relationship"] = "template_variant"
        result["confidence"] = float(verification.confidence)
        result["core_concept"] = None
        result["reason"] = verification.reason
        return result

    result["decision"] = "uncertain"
    result["relationship"] = "uncertain"
    result["confidence"] = float(verification.confidence)
    result["reason"] = verification.reason
    return result


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
        raise ValueError("family calibration pairs missing required columns: " + ", ".join(missing))

    eligible: list[dict[str, Any]] = []
    missing_evidence = 0
    prompt_too_large = 0

    for row in pairs.to_dict(orient="records"):
        if is_truthy(row.get("same_current_family")):
            continue

        combined = parse_optional_number(row.get("combined_score"))
        structure = parse_optional_number(row.get("structure_score"))
        if combined is None or structure is None:
            continue

        deterministic_gate = classify_pair(row)
        reason: str | None = None
        if deterministic_gate is not None:
            reason = f"preview_gate:{deterministic_gate}"
        elif combined >= min_combined:
            reason = "borderline_combined"
        elif (
            is_truthy(row.get("cross_language"))
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
        cross_priority = 0 if is_truthy(row.get("cross_language")) else 1
        combined = parse_optional_number(row.get("combined_score")) or 0.0
        structure = parse_optional_number(row.get("structure_score")) or 0.0
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


def merge_judgment_frames(
    existing: pd.DataFrame | None,
    batch: pd.DataFrame,
    *,
    model: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    if existing is None or existing.empty:
        compatible = pd.DataFrame()
        incompatible_rows = 0
    else:
        work = existing.copy()
        required_version_columns = {
            "model",
            "prompt_version",
            "judge_schema_version",
        }
        if required_version_columns.issubset(work.columns):
            mask = (
                work["model"].astype(str).eq(model)
                & work["prompt_version"].astype(str).eq(PROMPT_VERSION)
                & work["judge_schema_version"].astype(str).eq(JUDGE_SCHEMA_VERSION)
            )
            compatible = work.loc[mask].copy()
            incompatible_rows = int((~mask).sum())
        else:
            compatible = pd.DataFrame()
            incompatible_rows = int(len(work))

    existing_rows = int(len(compatible))
    batch_rows = int(len(batch))

    frames = [frame for frame in (compatible, batch) if frame is not None and not frame.empty]
    if not frames:
        merged = pd.DataFrame()
    else:
        merged = pd.concat(frames, ignore_index=True, sort=False)
        if "pair_id" not in merged.columns:
            raise ValueError("AI judgment output missing pair_id")
        merged = (
            merged.drop_duplicates(subset=["pair_id"], keep="last")
            .sort_values("pair_id", kind="mergesort")
            .reset_index(drop=True)
        )

    stats = {
        "existing_compatible_rows": existing_rows,
        "existing_incompatible_rows_ignored": incompatible_rows,
        "batch_judged_rows": batch_rows,
        "cumulative_judged_rows": int(len(merged)),
        "new_or_replaced_pairs": (
            int(
                len(
                    set(batch["pair_id"].astype(str))
                    if not batch.empty and "pair_id" in batch.columns
                    else set()
                )
            )
        ),
    }
    return merged, stats


def model_pricing(
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


def estimate_usage_cost(
    input_tokens: int,
    output_tokens: int,
    input_rate: float | None,
    output_rate: float | None,
) -> float | None:
    if input_rate is None or output_rate is None:
        return None
    return float(input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate)


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
    input_rate, output_rate, pricing_source = model_pricing(
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
            int(selection_report["estimated_input_tokens_selected"]) + estimated_output_tokens
        ),
        "input_usd_per_million": input_rate,
        "output_usd_per_million": output_rate,
        "pricing_source": pricing_source,
        "estimated_cost_usd_ceiling": estimate_usage_cost(
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
