"""Command-line adapter for vision slides workflow."""

from __future__ import annotations

import argparse

import creative_research.vision.slides as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="CSV manifest")
    parser.add_argument("--out", default="visual_study_v2")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--max-posts", type=int, default=None)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Randomly sample N manifest rows for validation.",
    )
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--retry-base-seconds", type=float, default=2.0)
    parser.add_argument("--sleep-between", type=float, default=0.2)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.analyze_manifest(service.SlideshowAnalysisOptions(**vars(args)))


if __name__ == "__main__":
    main()
