from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.knowledge_reviews import load_knowledge_reviews
from creative_research.stages.promote_knowledge import build_knowledge_tables


def _hypothesis(
    hypothesis_id: str,
    hypothesis_type: str,
    *,
    scope_type: str = "operator",
    scope_id: str = "OP1",
    operator_id: str = "OP1",
    account_id: str | None = None,
    confidence: float = 0.84,
    readiness: str = "strong_candidate",
    summary: dict | None = None,
    patterns: list[str] | None = None,
    counters: list[str] | None = None,
):
    return {
        "hypothesis_id": hypothesis_id,
        "hypothesis_type": hypothesis_type,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "operator_id": operator_id,
        "account_id": account_id,
        "title": hypothesis_type,
        "claim": hypothesis_type,
        "status": "hypothesis",
        "causal_claim": False,
        "confidence_score": confidence,
        "confidence_band": "high" if confidence >= 0.8 else "medium",
        "evidence_strength": "high" if confidence >= 0.8 else "medium",
        "promotion_readiness": readiness,
        "supporting_patterns_count": len(patterns or ["PAT-1"]),
        "counter_patterns_count": len(counters or []),
        "independent_pattern_types_count": 2,
        "sample_size_total": 30,
        "supporting_pattern_ids_json": json.dumps(patterns or ["PAT-1"]),
        "counter_pattern_ids_json": json.dumps(counters or []),
        "evidence_summary_json": json.dumps(summary or {}),
        "counter_evidence_json": json.dumps({}),
        "alternative_explanations_json": json.dumps(["alternative"]),
        "valid_from": None,
        "valid_to": None,
        "inference_method": "test",
    }


def _hypotheses() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _hypothesis(
                "STR-ORIGIN",
                "account_origin_exploration",
                scope_type="account",
                scope_id="A",
                account_id="A",
                confidence=0.78,
                readiness="review",
                summary={
                    "originator_signal": 0.8,
                    "receiver_signal": 0.1,
                },
                patterns=["PAT-A"],
            ),
            _hypothesis(
                "STR-RECEIVE",
                "account_reuse_amplification",
                scope_type="account",
                scope_id="B",
                account_id="B",
                confidence=0.79,
                readiness="review",
                summary={
                    "originator_signal": 0.1,
                    "receiver_signal": 0.85,
                    "amplifier_signal": 0.7,
                },
                patterns=["PAT-B"],
            ),
            _hypothesis(
                "STR-MODEL",
                "operator_explore_propagate_model",
                summary={
                    "origin_accounts": ["A"],
                    "receiver_accounts": ["B"],
                },
                patterns=["PAT-A", "PAT-B", "PAT-REUSE"],
            ),
            _hypothesis(
                "STR-MUTATION",
                "preserve_core_vary_execution",
                summary={
                    "preserved_core_dimensions": [
                        "content_angle",
                        "sequence_roles",
                    ],
                    "changed_execution_dimensions": [
                        "hook_text",
                        "format",
                    ],
                },
                patterns=["PAT-ANGLE", "PAT-SEQ", "PAT-HOOK", "PAT-FORMAT"],
            ),
            _hypothesis(
                "STR-ITERATE",
                "iterative_reuse_model",
                confidence=0.82,
                summary={
                    "multi_post_family_rate": 0.72,
                    "cross_account_family_rate": 0.4,
                    "median_family_lifespan_days": 6.0,
                },
                patterns=["PAT-REUSE"],
            ),
            _hypothesis(
                "STR-CADENCE",
                "performance_responsive_cadence",
                confidence=0.70,
                readiness="review",
                summary={
                    "direction": "longer",
                    "level": "operator",
                },
                patterns=["PAT-CADENCE"],
            ),
        ]
    )


def _families() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "family_id": "F1",
                "operator_id": "OP1",
                "origin_account": "a",
                "first_seen": "2026-01-01",
                "last_seen": "2026-01-10",
                "member_count": 5,
                "variant_count": 4,
                "accounts_count": 2,
                "cross_account": True,
                "representative_post_uid": "P2",
                "anchor_cohesion_mean": 0.85,
                "anchor_cohesion_min": 0.72,
                "family_confidence": "high",
                "core_angle": "study_method",
                "core_hook_text": "3 study mistakes",
                "core_hook_formula": "N mistakes + audience",
                "core_creative_formula": "hook -> problem -> proof -> CTA",
                "core_sequence_roles_json": json.dumps(
                    ["hook", "problem", "proof", "cta"]
                ),
                "median_views_percentile_account": 0.78,
                "max_views_percentile_account": 0.95,
            },
            {
                "family_id": "F2",
                "operator_id": "OP1",
                "origin_account": "b",
                "first_seen": "2026-02-01",
                "last_seen": "2026-02-05",
                "member_count": 2,
                "variant_count": 1,
                "accounts_count": 1,
                "cross_account": False,
                "representative_post_uid": "P6",
                "anchor_cohesion_mean": 0.80,
                "anchor_cohesion_min": 0.75,
                "family_confidence": "high",
                "core_angle": "productivity",
                "core_hook_text": "morning routine",
                "core_hook_formula": "POV + routine",
                "core_creative_formula": "hook -> routine -> ending",
                "core_sequence_roles_json": json.dumps(
                    ["hook", "value", "ending"]
                ),
                "median_views_percentile_account": 0.60,
                "max_views_percentile_account": 0.70,
            },
        ]
    )


def _members() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"family_id": "F1", "post_uid": f"P{i}", "account_id": "A" if i < 3 else "B"}
            for i in range(1, 6)
        ]
    )


def _evidence() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "hypothesis_id": "STR-MUTATION",
                "pattern_id": "PAT-HOOK",
                "relation": "support",
                "post_uid": "P2",
                "family_id": "F1",
                "account_id": "B",
                "link_role": "support",
                "detail": "hook changed",
            },
            {
                "hypothesis_id": "STR-MODEL",
                "pattern_id": "PAT-A",
                "relation": "support",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
                "link_role": "support",
                "detail": "origin",
            },
        ]
    )


def test_knowledge_promotion_builds_all_typed_banks_and_lineage() -> None:
    tables = build_knowledge_tables(
        _hypotheses(),
        _evidence(),
        _families(),
        _members(),
    )

    catalog = tables["knowledge_catalog"]
    assert {"strategy", "rule", "lesson", "template", "playbook"}.issubset(
        set(catalog["knowledge_type"])
    )

    templates = tables["templates"]
    family_templates = templates.loc[
        templates["subtype"].eq("creative_family_structure")
    ]
    assert len(family_templates) == 1
    payload = json.loads(family_templates.iloc[0]["payload_json"])
    assert payload["sequence_roles"] == ["hook", "problem", "proof", "cta"]
    assert family_templates.iloc[0]["knowledge_status"] == "promoted"

    rules = tables["rules"]
    adaptation_rule = rules.loc[
        rules["subtype"].eq("preserve_core_vary_execution")
    ].iloc[0]
    assert "content_angle" in adaptation_rule["statement"]
    assert "hook_text" in adaptation_rule["statement"]

    playbook = tables["playbooks"].iloc[0]
    steps = json.loads(playbook["payload_json"])["steps"]
    assert len(steps) >= 4
    assert steps[0]["accounts"] == ["A"]
    assert steps[2]["accounts"] == ["B"]

    evidence = tables["knowledge_evidence_links"]
    assert "P2" in set(evidence["post_uid"].dropna())
    assert "F1" in set(evidence["family_id"].dropna())


def test_manual_review_can_approve_or_reject_source_items(tmp_path: Path) -> None:
    path = tmp_path / "reviews.toml"
    path.write_text(
        """
[[reviews]]
source_type = "hypothesis"
source_id = "STR-ORIGIN"
decision = "approve"

[[reviews]]
source_type = "family"
source_id = "F1"
decision = "reject"
""".strip(),
        encoding="utf-8",
    )
    reviews = load_knowledge_reviews(path)
    tables = build_knowledge_tables(
        _hypotheses(),
        _evidence(),
        _families(),
        _members(),
        reviews=reviews,
    )

    strategies = tables["strategies"]
    origin = strategies.loc[
        strategies["source_ids_json"].str.contains("STR-ORIGIN")
    ].iloc[0]
    assert origin["knowledge_status"] == "approved"

    template = tables["templates"].loc[
        tables["templates"]["subtype"].eq("creative_family_structure")
    ].iloc[0]
    assert template["knowledge_status"] == "rejected"


def test_low_confidence_hypotheses_are_not_promoted_to_knowledge() -> None:
    hypotheses = _hypotheses()
    hypotheses.loc[
        hypotheses["hypothesis_id"].eq("STR-CADENCE"),
        "confidence_score",
    ] = 0.40

    tables = build_knowledge_tables(
        hypotheses,
        _evidence(),
        _families(),
        _members(),
        min_confidence=0.60,
    )
    lessons = tables["lessons"]
    assert not lessons["source_ids_json"].str.contains("STR-CADENCE").any()
