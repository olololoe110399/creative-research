"""Command-line adapters for human knowledge reviews."""

from __future__ import annotations

import argparse

from creative_research.infrastructure.knowledge_reviews import ALLOWED_DECISIONS
from creative_research.pipeline import reviews as workflow


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Build and apply a human review queue for evidence-derived knowledge.")
    )
    subparsers = parser.add_subparsers(dest="action", required=False)

    queue_parser = subparsers.add_parser(
        "queue",
        help="Generate prioritized source-level review queue.",
    )
    queue_parser.add_argument(
        "--hypotheses",
        default="data/06_analytics/strategy_hypotheses.parquet",
    )
    queue_parser.add_argument(
        "--strategy-evidence",
        default="data/06_analytics/strategy_evidence_links.parquet",
    )
    queue_parser.add_argument(
        "--families",
        default="data/06_analytics/creative_families.parquet",
    )
    queue_parser.add_argument(
        "--family-members",
        default="data/06_analytics/creative_family_members.parquet",
    )
    queue_parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
    )
    queue_parser.add_argument(
        "--out",
        default="data/07_knowledge/review",
    )
    queue_parser.add_argument("--include-reviewed", action="store_true")
    queue_parser.add_argument("--show", type=int, default=10)

    decide_parser = subparsers.add_parser(
        "decide",
        help="Write one approve/reject/hold review decision.",
    )
    decide_parser.add_argument("source_type")
    decide_parser.add_argument("source_id")
    decide_parser.add_argument(
        "--decision",
        required=True,
        choices=sorted(ALLOWED_DECISIONS),
    )
    decide_parser.add_argument("--note")
    decide_parser.add_argument("--reviewed-by")
    decide_parser.add_argument("--reviewed-at")
    decide_parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply non-empty decisions from the editable decisions CSV.",
    )
    apply_parser.add_argument(
        "--decisions",
        default=("data/07_knowledge/review/knowledge_review_decisions.csv"),
    )
    apply_parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
    )
    apply_parser.add_argument("--reviewed-by")

    args = parser.parse_args()
    action = args.action or "queue"
    if action == "queue":
        if args.action is None:
            args = queue_parser.parse_args([])
        workflow.queue_reviews(
            workflow.ReviewQueueOptions(
                **{key: value for key, value in vars(args).items() if key != "action"}
            )
        )
    elif action == "decide":
        workflow.decide_review(
            workflow.ReviewDecisionOptions(
                **{key: value for key, value in vars(args).items() if key != "action"}
            )
        )
    elif action == "apply":
        workflow.apply_reviews(
            workflow.ReviewImportOptions(
                **{key: value for key, value in vars(args).items() if key != "action"}
            )
        )
    else:
        raise SystemExit(f"Unknown review action: {action}")


if __name__ == "__main__":
    main()
