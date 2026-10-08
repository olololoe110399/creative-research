from __future__ import annotations

from pathlib import Path

import pytest

from creative_research.knowledge_reviews import load_knowledge_reviews


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
