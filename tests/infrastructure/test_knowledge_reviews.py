from __future__ import annotations

from pathlib import Path

import pytest

from creative_research.infrastructure.knowledge_reviews import (
    KnowledgeReview,
    load_knowledge_reviews,
    upsert_knowledge_reviews,
)


def test_load_knowledge_reviews(tmp_path: Path) -> None:
    path = tmp_path / "reviews.toml"
    path.write_text(
        """
schema_version = "knowledge-review-v1"

[[reviews]]
source_type = "hypothesis"
source_id = "STR-001"
decision = "approve"
note = "Reviewed against source posts."
reviewed_by = "researcher"
reviewed_at = "2026-10-08"
""".strip(),
        encoding="utf-8",
    )
    reviews = load_knowledge_reviews(path)
    review = reviews[("hypothesis", "STR-001")]
    assert review.decision == "approve"
    assert review.note == "Reviewed against source posts."


def test_reject_invalid_review_decision(tmp_path: Path) -> None:
    path = tmp_path / "reviews.toml"
    path.write_text(
        """
[[reviews]]
source_type = "hypothesis"
source_id = "STR-001"
decision = "maybe"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="decision"):
        load_knowledge_reviews(path)


def test_upsert_knowledge_reviews_creates_and_replaces_entries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reviews.toml"
    upsert_knowledge_reviews(
        path,
        [
            KnowledgeReview(
                source_type="hypothesis",
                source_id="STR-001",
                decision="approve",
                note="Strong evidence.",
                reviewed_by="researcher",
                reviewed_at="2026-10-09T00:00:00+00:00",
            ),
            KnowledgeReview(
                source_type="family",
                source_id="FAM-001",
                decision="hold",
            ),
        ],
    )
    first = load_knowledge_reviews(path)
    assert first[("hypothesis", "STR-001")].decision == "approve"
    assert first[("family", "FAM-001")].decision == "hold"

    upsert_knowledge_reviews(
        path,
        [
            KnowledgeReview(
                source_type="hypothesis",
                source_id="STR-001",
                decision="reject",
                note="Counter evidence changed the decision.",
            )
        ],
    )
    second = load_knowledge_reviews(path)
    assert second[("hypothesis", "STR-001")].decision == "reject"
    assert second[("family", "FAM-001")].decision == "hold"

    text = path.read_text(encoding="utf-8")
    assert 'schema_version = "knowledge-review-v1"' in text
    assert "Counter evidence changed the decision." in text
