from __future__ import annotations

import json

import pandas as pd

from creative_research.stages.infer_strategies import build_strategy_hypothesis_tables


def _pattern(
    pattern_id: str,
    pattern_type: str,
    *,
    scope_type: str = "operator",
    scope_id: str = "OP1",
    operator_id: str = "OP1",
    sample_size: int = 20,
    support_rate: float | None = 0.8,
    effect_size: float | None = 0.3,
    evidence_strength: str = "medium",
    metrics: dict | None = None,
    counter: dict | None = None,
):
    return {
        "pattern_id": pattern_id,
        "pattern_type": pattern_type,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "operator_id": operator_id,
        "title": pattern_id,
        "observation": pattern_id,
        "sample_size": sample_size,
        "support_count": 10,
        "support_rate": support_rate,
        "effect_size": effect_size,
        "evidence_strength": evidence_strength,
        "metrics_json": json.dumps(metrics or {}),
        "counter_evidence_json": json.dumps(counter or {}),
        "causal_claim": False,
    }


def _patterns() -> pd.DataFrame:
    rows = [
        _pattern(
            "PAT-A-ORIGIN",
            "account_flow_profile",
            scope_type="account",
            scope_id="A",
            metrics={
                "family_origin_rate": 0.82,
                "imported_family_rate": 0.15,
                "outbound_propagation_rate": 0.78,
                "cross_account_participation_rate": 0.70,
                "originator_signal": 0.80,
                "receiver_signal": 0.15,
                "amplifier_signal": 0.30,
                "evidence_strength": "high",
            },
            evidence_strength="high",
        ),
        _pattern(
            "PAT-B-RECEIVE",
            "account_flow_profile",
            scope_type="account",
            scope_id="B",
            metrics={
                "family_origin_rate": 0.10,
                "imported_family_rate": 0.84,
                "outbound_propagation_rate": 0.20,
                "cross_account_participation_rate": 0.76,
                "originator_signal": 0.14,
                "receiver_signal": 0.84,
                "amplifier_signal": 0.72,
                "evidence_strength": "high",
            },
            evidence_strength="high",
        ),
        _pattern(
            "PAT-REUSE",
            "family_reuse_baseline",
            metrics={
                "multi_post_family_rate": 0.72,
                "cross_account_family_rate": 0.46,
                "median_family_lifespan_days": 6.0,
            },
            effect_size=None,
            support_rate=0.72,
            evidence_strength="high",
            sample_size=40,
            counter={"singleton_families": 11},
        ),
        _pattern(
            "PAT-ANGLE-PRESERVE",
            "propagation_dimension_behavior",
            metrics={
                "dimension": "content_angle",
                "dominant_action": "preserved",
                "changed_rate": 0.10,
                "preserved_rate": 0.90,
            },
            support_rate=0.90,
            effect_size=0.40,
            evidence_strength="high",
        ),
        _pattern(
            "PAT-SEQ-PRESERVE",
            "propagation_dimension_behavior",
            metrics={
                "dimension": "sequence_roles",
                "dominant_action": "preserved",
                "changed_rate": 0.20,
                "preserved_rate": 0.80,
            },
            support_rate=0.80,
            effect_size=0.30,
        ),
        _pattern(
            "PAT-HOOK-CHANGE",
            "propagation_dimension_behavior",
            metrics={
                "dimension": "hook_text",
                "dominant_action": "changed",
                "changed_rate": 0.88,
                "preserved_rate": 0.12,
            },
            support_rate=0.88,
            effect_size=0.38,
            evidence_strength="high",
        ),
        _pattern(
            "PAT-FORMAT-CHANGE",
            "propagation_dimension_behavior",
            metrics={
                "dimension": "format",
                "dominant_action": "changed",
                "changed_rate": 0.75,
                "preserved_rate": 0.25,
            },
            support_rate=0.75,
            effect_size=0.25,
        ),
        _pattern(
            "PAT-CADENCE",
            "cadence_after_performance",
            metrics={
                "level": "operator",
                "high_median_gap_hours": 12.0,
                "low_median_gap_hours": 4.0,
                "normalized_gap_difference": 2.0,
            },
            effect_size=2.0,
            support_rate=None,
            evidence_strength="medium",
        ),
        _pattern(
            "PAT-SHIFT",
            "strategy_change_point",
            metrics={
                "previous_period": "2026-01",
                "current_period": "2026-02",
                "change_score": 0.62,
                "changed_dimensions": ["hook_technique", "product_rate"],
            },
            effect_size=0.62,
            support_rate=None,
            evidence_strength="high",
        ),
    ]
    return pd.DataFrame(rows)


def _evidence_links() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pattern_id": "PAT-A-ORIGIN",
                "post_uid": "P1",
                "family_id": "F1",
                "account_id": "A",
                "link_role": "support",
                "detail": "origin evidence",
            },
            {
                "pattern_id": "PAT-B-RECEIVE",
                "post_uid": "P2",
                "family_id": "F1",
                "account_id": "B",
                "link_role": "support",
                "detail": "receiver evidence",
            },
            {
                "pattern_id": "PAT-HOOK-CHANGE",
                "post_uid": "P2",
                "family_id": "F1",
                "account_id": "B",
                "link_role": "support",
                "detail": "hook changed",
            },
            {
                "pattern_id": "PAT-SHIFT",
                "post_uid": "P9",
                "family_id": None,
                "account_id": "A",
                "link_role": "current_window",
                "detail": "2026-02",
            },
        ]
    )


def test_strategy_inference_builds_account_and_operator_hypotheses() -> None:
    tables = build_strategy_hypothesis_tables(_patterns(), _evidence_links())
    hypotheses = tables["strategy_hypotheses"]

    types = set(hypotheses["hypothesis_type"])
    assert "account_origin_exploration" in types
    assert "account_reuse_amplification" in types
    assert "operator_explore_propagate_model" in types
    assert "preserve_core_vary_execution" in types
    assert "iterative_reuse_model" in types
    assert "performance_responsive_cadence" in types
    assert "temporal_strategy_shift" in types

    origin = hypotheses.loc[
        hypotheses["hypothesis_type"] == "account_origin_exploration"
    ].iloc[0]
    assert origin["scope_id"] == "A"
    assert origin["confidence_score"] <= 0.82
    assert origin["causal_claim"] == False  # noqa: E712
    alternatives = json.loads(origin["alternative_explanations_json"])
    assert len(alternatives) >= 2

    model = hypotheses.loc[
        hypotheses["hypothesis_type"] == "operator_explore_propagate_model"
    ].iloc[0]
    summary = json.loads(model["evidence_summary_json"])
    assert summary["origin_accounts"] == ["A"]
    assert summary["receiver_accounts"] == ["B"]
    assert model["supporting_patterns_count"] >= 2


def test_mutation_hypothesis_keeps_supporting_patterns_and_inherited_evidence() -> None:
    tables = build_strategy_hypothesis_tables(_patterns(), _evidence_links())
    hypotheses = tables["strategy_hypotheses"]
    mutation = hypotheses.loc[
        hypotheses["hypothesis_type"] == "preserve_core_vary_execution"
    ].iloc[0]
    summary = json.loads(mutation["evidence_summary_json"])
    assert "content_angle" in summary["preserved_core_dimensions"]
    assert "hook_text" in summary["changed_execution_dimensions"]

    links = tables["strategy_pattern_links"].loc[
        tables["strategy_pattern_links"]["hypothesis_id"].eq(
            mutation["hypothesis_id"]
        )
    ]
    assert "PAT-HOOK-CHANGE" in set(links["pattern_id"])
    assert "PAT-ANGLE-PRESERVE" in set(links["pattern_id"])

    inherited = tables["strategy_evidence_links"].loc[
        tables["strategy_evidence_links"]["hypothesis_id"].eq(
            mutation["hypothesis_id"]
        )
    ]
    assert "P2" in set(inherited["post_uid"].dropna())


def test_low_evidence_account_flow_does_not_become_role_hypothesis() -> None:
    patterns = _patterns()
    extra = _pattern(
        "PAT-C-LOW",
        "account_flow_profile",
        scope_type="account",
        scope_id="C",
        sample_size=2,
        evidence_strength="low",
        metrics={
            "family_origin_rate": 0.9,
            "imported_family_rate": 0.0,
            "outbound_propagation_rate": 1.0,
            "originator_signal": 0.95,
            "receiver_signal": 0.0,
            "amplifier_signal": 0.0,
        },
    )
    patterns = pd.concat([patterns, pd.DataFrame([extra])], ignore_index=True)

    hypotheses = build_strategy_hypothesis_tables(patterns)["strategy_hypotheses"]
    c_rows = hypotheses.loc[hypotheses["scope_id"].astype(str).eq("C")]
    assert c_rows.empty
