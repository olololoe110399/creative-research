"""Command-line adapter for judge family candidates workflow."""

from __future__ import annotations

import argparse

import creative_research.vision.families as service
from creative_research.analysis.family_judgments import (
    DEFAULT_CROSS_LANGUAGE_MIN_COMBINED,
    DEFAULT_CROSS_LANGUAGE_MIN_STRUCTURE,
    DEFAULT_MAX_AI_PAIRS,
    DEFAULT_MAX_API_CALLS,
    DEFAULT_MAX_ESTIMATED_INPUT_TOKENS,
    DEFAULT_MAX_INPUT_TOKENS_PER_PAIR,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TRANSLATION_VERIFIER_CALLS,
    DEFAULT_MIN_COMBINED,
    DEFAULT_MODEL,
    DEFAULT_TRANSLATION_VERIFIER_MAX_OUTPUT_TOKENS,
    DEFAULT_TRANSLATION_VERIFIER_MIN_CONFIDENCE,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Judge ambiguous creative-family candidate pairs with Gemini using "
            "existing Vision evidence only. No performance metrics are sent."
        )
    )
    parser.add_argument(
        "--pairs",
        default=("data/06_analytics/family_calibration/family_calibration_pairs.parquet"),
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
    parser.add_argument(
        "--translation-verifier-max-output-tokens",
        type=int,
        default=DEFAULT_TRANSLATION_VERIFIER_MAX_OUTPUT_TOKENS,
    )
    parser.add_argument(
        "--max-translation-verifier-calls",
        type=int,
        default=DEFAULT_MAX_TRANSLATION_VERIFIER_CALLS,
    )
    parser.add_argument(
        "--translation-verifier-min-confidence",
        type=float,
        default=DEFAULT_TRANSLATION_VERIFIER_MIN_CONFIDENCE,
    )
    parser.add_argument("--skip-translation-verifier", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.judge_candidates(service.FamilyJudgmentOptions(**vars(args)))


if __name__ == "__main__":
    main()
