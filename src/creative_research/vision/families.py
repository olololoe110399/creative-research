"""Plan and export cached family judgments without mutating production families."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from creative_research.analysis.family_judgments import (
    TRANSLATION_VERIFIER_PROMPT_VERSION,
    TRANSLATION_VERIFIER_SCHEMA_VERSION,
    build_plan,
    estimate_usage_cost,
    merge_judgment_frames,
    parse_optional_number,
)
from creative_research.infrastructure.config import RuntimeSettings
from creative_research.infrastructure.gemini import gemini_client
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import (
    atomic_output,
    read_table,
    write_csv,
    write_parquet,
)
from creative_research.infrastructure.storage import write_text as atomic_write_text
from creative_research.vision.family_judging import (
    execute_judgments,
    verify_translation_judgments,
)


@dataclass(frozen=True, slots=True)
class FamilyJudgmentOptions:
    """CLI-independent parameters for this workflow."""

    pairs: str
    analysis: str
    sequence: str
    out: str
    model: str
    min_combined: float
    cross_language_min_combined: float
    cross_language_min_structure: float
    max_ai_pairs: int
    max_api_calls: int
    max_input_tokens_per_pair: int
    max_estimated_input_tokens: int
    max_output_tokens: int
    input_usd_per_million: float | None
    output_usd_per_million: float | None
    retries: int
    retry_base_seconds: float
    sleep_between: float
    translation_verifier_max_output_tokens: int
    max_translation_verifier_calls: int
    translation_verifier_min_confidence: float
    skip_translation_verifier: bool
    dry_run: bool
    force: bool


def judge_candidates(options: FamilyJudgmentOptions) -> None:

    pairs_path = resolve_path(options.pairs)
    analysis_path = resolve_path(options.analysis)
    sequence_path = resolve_path(options.sequence)
    out_dir = resolve_path(options.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = read_table(pairs_path)
    analysis = read_table(analysis_path)
    sequence = read_table(sequence_path) if sequence_path.exists() else None

    selected, plan, evidence_lookup = build_plan(
        pairs,
        analysis,
        sequence,
        model=options.model,
        min_combined=options.min_combined,
        cross_language_min_combined=options.cross_language_min_combined,
        cross_language_min_structure=options.cross_language_min_structure,
        max_ai_pairs=max(0, options.max_ai_pairs),
        max_input_tokens_per_pair=max(1, options.max_input_tokens_per_pair),
        max_estimated_input_tokens=max(1, options.max_estimated_input_tokens),
        max_output_tokens=max(1, options.max_output_tokens),
        input_usd_per_million=options.input_usd_per_million,
        output_usd_per_million=options.output_usd_per_million,
    )

    plan.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "pairs_source": str(pairs_path),
            "analysis_source": str(analysis_path),
            "sequence_source": (str(sequence_path) if sequence is not None else None),
            "dry_run": options.dry_run,
            "max_api_calls": max(1, options.max_api_calls),
            "translation_verifier_enabled": (not options.skip_translation_verifier),
            "translation_verifier_schema_version": (TRANSLATION_VERIFIER_SCHEMA_VERSION),
            "translation_verifier_prompt_version": (TRANSLATION_VERIFIER_PROMPT_VERSION),
            "translation_verifier_max_output_tokens": max(
                1,
                options.translation_verifier_max_output_tokens,
            ),
            "max_translation_verifier_calls": max(
                1,
                options.max_translation_verifier_calls,
            ),
            "translation_verifier_min_confidence": min(
                1.0,
                max(0.0, options.translation_verifier_min_confidence),
            ),
        }
    )

    print("Family AI judgment plan:")
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    plan_path = out_dir / "family_ai_plan.json"
    atomic_write_text(plan_path, json.dumps(plan, ensure_ascii=False, indent=2))
    if options.dry_run:
        return

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Run with --dry-run to inspect "
            "pair/token/cost planning without an API key."
        )

    with gemini_client(key, timeout_seconds=RuntimeSettings.from_environ().ai_timeout) as client:
        cache_path = out_dir / "family_ai_cache.jsonl"
        judgments, execution = execute_judgments(
            selected,
            evidence_lookup,
            model=options.model,
            cache_path=cache_path,
            max_output_tokens=max(1, options.max_output_tokens),
            max_estimated_input_tokens=max(1, options.max_estimated_input_tokens),
            max_api_calls=max(1, options.max_api_calls),
            retries=max(0, options.retries),
            retry_base_seconds=max(0.0, options.retry_base_seconds),
            sleep_between=max(0.0, options.sleep_between),
            force=options.force,
            client=client,
        )

        translation_verifier_cache_path = out_dir / "family_ai_translation_verifier_cache.jsonl"
        if options.skip_translation_verifier:
            translation_report = {
                "translation_verifier_candidates": 0,
                "translation_verifier_api_calls": 0,
                "translation_verifier_api_attempts": 0,
                "translation_verifier_cache_hits": 0,
                "translation_verifier_failures": 0,
                "translation_verifier_actual_input_tokens": 0,
                "translation_verifier_actual_output_tokens": 0,
                "translation_verifier_actual_total_tokens": 0,
                "translation_verifier_final_counts": {},
                "translation_verifier_min_confidence": (
                    min(
                        1.0,
                        max(
                            0.0,
                            options.translation_verifier_min_confidence,
                        ),
                    )
                ),
            }
        else:
            judgments, translation_report = verify_translation_judgments(
                judgments,
                model=options.model,
                cache_path=translation_verifier_cache_path,
                max_output_tokens=max(
                    1,
                    options.translation_verifier_max_output_tokens,
                ),
                max_calls=max(
                    1,
                    options.max_translation_verifier_calls,
                ),
                min_confidence=min(
                    1.0,
                    max(
                        0.0,
                        options.translation_verifier_min_confidence,
                    ),
                ),
                retries=max(0, options.retries),
                retry_base_seconds=max(
                    0.0,
                    options.retry_base_seconds,
                ),
                sleep_between=max(0.0, options.sleep_between),
                force=options.force,
                client=client,
            )

    judgments_path = out_dir / "family_ai_judgments.parquet"
    jsonl_path = out_dir / "family_ai_judgments.jsonl"
    review_path = out_dir / "family_ai_review.csv"
    report_path = out_dir / "family_ai_report.json"

    existing_judgments = read_table(judgments_path) if judgments_path.exists() else None
    cumulative_judgments, merge_stats = merge_judgment_frames(
        existing_judgments,
        judgments,
        model=options.model,
    )

    write_parquet(judgments_path, cumulative_judgments)
    with atomic_output(jsonl_path) as temporary:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in cumulative_judgments.to_dict(orient="records"):
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    review_columns = [
        "pair_id",
        "left_account",
        "right_account",
        "left_language",
        "right_language",
        "cross_language",
        "left_angle",
        "right_angle",
        "left_hook_text",
        "right_hook_text",
        "left_topic",
        "right_topic",
        "combined_score",
        "structure_score",
        "semantic_text_score",
        "decision",
        "relationship",
        "confidence",
        "core_concept",
        "reason",
        "candidate_reason",
        "judgment_source",
        "primary_decision",
        "primary_relationship",
        "primary_confidence",
        "translation_verifier_equivalence",
        "translation_verifier_type",
        "translation_verifier_confidence",
        "translation_verifier_left_central_idea",
        "translation_verifier_right_central_idea",
        "translation_verifier_reason",
        "translation_verifier_source",
    ]
    available_review_columns = [
        column for column in review_columns if column in cumulative_judgments.columns
    ]
    write_csv(
        review_path,
        cumulative_judgments.loc[:, available_review_columns],
        index=False,
        encoding="utf-8-sig",
    )

    input_rate = parse_optional_number(plan.get("input_usd_per_million"))
    output_rate = parse_optional_number(plan.get("output_usd_per_million"))
    actual_cost = None
    if (
        execution["actual_input_tokens"] is not None
        and execution["actual_output_tokens"] is not None
    ):
        actual_cost = estimate_usage_cost(
            int(execution["actual_input_tokens"]),
            int(execution["actual_output_tokens"]),
            input_rate,
            output_rate,
        )

    translation_verifier_cost = estimate_usage_cost(
        int(
            parse_optional_number(
                translation_report.get(
                    "translation_verifier_actual_input_tokens",
                    0,
                )
            )
            or 0
        ),
        int(
            parse_optional_number(
                translation_report.get(
                    "translation_verifier_actual_output_tokens",
                    0,
                )
            )
            or 0
        ),
        input_rate,
        output_rate,
    )
    total_actual_cost = (actual_cost or 0.0) + (translation_verifier_cost or 0.0)

    report = {
        **plan,
        **execution,
        **translation_report,
        **merge_stats,
        "cumulative_decision_counts": (
            cumulative_judgments["decision"].value_counts().to_dict()
            if not cumulative_judgments.empty and "decision" in cumulative_judgments.columns
            else {}
        ),
        "cumulative_relationship_counts": (
            cumulative_judgments["relationship"].value_counts().to_dict()
            if not cumulative_judgments.empty and "relationship" in cumulative_judgments.columns
            else {}
        ),
        "actual_cost_usd_estimate": actual_cost,
        "translation_verifier_actual_cost_usd_estimate": (translation_verifier_cost),
        "total_actual_cost_usd_estimate": total_actual_cost,
        "outputs": {
            "plan": str(plan_path),
            "judgments": str(judgments_path),
            "judgments_jsonl": str(jsonl_path),
            "review_csv": str(review_path),
            "cache": str(cache_path),
            "translation_verifier_cache": str(translation_verifier_cache_path),
            "report": str(report_path),
        },
        "notes": [
            "No scrape was performed.",
            "No Vision creative re-analysis was performed.",
            "Performance metrics were not included in AI prompts.",
            "AI judgments are inferred evidence and do not mutate production families.",
            "Cache identity includes pair, evidence hash, model, prompt version, and judge schema version.",
            "Judgment outputs are cumulative upserts by pair_id across compatible model/prompt/schema runs; incompatible historical rows are ignored.",
            "Primary translation_adaptation judgments are independently verified using hook/topic evidence only; app/product/format/sequence evidence is excluded from the verifier.",
        ],
    }
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
