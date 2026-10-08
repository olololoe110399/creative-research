from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REVIEW_SCHEMA_VERSION = "knowledge-review-v1"
ALLOWED_DECISIONS = {"approve", "reject", "hold"}


@dataclass(frozen=True, slots=True)
class KnowledgeReview:
    source_type: str
    source_id: str
    decision: str
    note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None


def load_knowledge_reviews(path: Path | None) -> dict[tuple[str, str], KnowledgeReview]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    schema_version = str(payload.get("schema_version") or REVIEW_SCHEMA_VERSION)
    if schema_version != REVIEW_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported knowledge review schema {schema_version!r}; "
            f"expected {REVIEW_SCHEMA_VERSION!r}"
        )

    raw_reviews = payload.get("reviews", [])
    if not isinstance(raw_reviews, list):
        raise ValueError("reviews must be an array of tables")

    result: dict[tuple[str, str], KnowledgeReview] = {}
    for index, raw in enumerate(raw_reviews, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"reviews[{index}] must be a table")

        source_type = str(raw.get("source_type") or "").strip()
        source_id = str(raw.get("source_id") or "").strip()
        decision = str(raw.get("decision") or "").strip().lower()
        if not source_type:
            raise ValueError(f"reviews[{index}].source_type is required")
        if not source_id:
            raise ValueError(f"reviews[{index}].source_id is required")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                f"reviews[{index}].decision must be one of "
                + ", ".join(sorted(ALLOWED_DECISIONS))
            )

        key = (source_type, source_id)
        if key in result:
            raise ValueError(
                f"Duplicate knowledge review for {source_type}:{source_id}"
            )
        result[key] = KnowledgeReview(
            source_type=source_type,
            source_id=source_id,
            decision=decision,
            note=(
                str(raw["note"]).strip()
                if raw.get("note") is not None
                else None
            ),
            reviewed_by=(
                str(raw["reviewed_by"]).strip()
                if raw.get("reviewed_by") is not None
                else None
            ),
            reviewed_at=(
                str(raw["reviewed_at"]).strip()
                if raw.get("reviewed_at") is not None
                else None
            ),
        )
    return result
