"""Presentation-only operating evidence and decision support.

This module does not change deterministic analytics, infer intent, or promote
knowledge.  A provisional playbook is never written to the trusted knowledge
catalog.  Its source hypothesis and manual-review state remain explicit.
"""

from __future__ import annotations

import json
from typing import Any


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _flow(row: dict[str, Any]) -> dict[str, Any]:
    """A chronology record, not evidence of causation or formal scale."""
    return {
        "family_id": _text(row.get("family_id")),
        "origin_account_id": _text(row.get("origin_account_id")),
        "origin_account": row.get("origin_account"),
        "target_account_id": _text(row.get("target_account_id")),
        "target_account": row.get("target_account"),
        "origin_post_uid": row.get("family_origin_post_uid"),
        "target_post_uid": row.get("target_first_post_uid"),
        "origin_created_at": row.get("origin_created_at"),
        "target_first_seen": row.get("target_first_seen"),
        "delay_days": row.get("delay_from_family_origin_days"),
        "origin_views_percentile_account": row.get("origin_views_percentile_account"),
        "target_views_percentile_account": row.get(
            "target_first_views_percentile_account"
        ),
        "target_outperformed_origin": row.get("target_outperformed_origin"),
        "preserved_dimensions": _json(row.get("preserved_dimensions_json"), []),
        "changed_dimensions": _json(row.get("changed_dimensions_json"), []),
    }


def empty_role_lineage() -> dict[str, Any]:
    return {
        "origin_families": [],
        "imported_families": [],
        "origin_family_count": 0,
        "imported_family_count": 0,
        "total_family_observations": 0,
    }


def build_role_flow_index(
    propagation: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build unique-family role denominators while retaining every target flow.

    An origin family sent to N receivers counts once in the originator numerator;
    all N original/receiving post pairs stay available for inspection. Imports
    count once per receiving account and family. This is the same population as
    the operator-level account role evidence, not the raw number of graph edges.
    """
    grouped: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    for raw in propagation:
        row = _flow(raw)
        family_id = row["family_id"]
        origin_id = row["origin_account_id"]
        target_id = row["target_account_id"]
        if not family_id or not origin_id or not target_id or origin_id == target_id:
            continue
        event_key = (
            family_id,
            origin_id,
            target_id,
            _text(row.get("target_post_uid")),
        )
        if event_key in seen:
            continue
        seen.add(event_key)
        for account_id, direction in (
            (origin_id, "origin"),
            (target_id, "import"),
        ):
            bucket = grouped.setdefault(
                account_id, {"origin": {}, "import": {}}
            )[direction]
            bucket.setdefault(family_id, []).append(row)

    result: dict[str, dict[str, Any]] = {}
    for account_id, directions in grouped.items():
        def summarize(which: str) -> list[dict[str, Any]]:
            return [
                {
                    "family_id": family_id,
                    "flows": sorted(
                        flows,
                        key=lambda item: (
                            _text(item.get("target_first_seen")),
                            _text(item.get("target_account_id")),
                            _text(item.get("target_post_uid")),
                        ),
                    ),
                }
                for family_id, flows in sorted(directions[which].items())
            ]

        origins = summarize("origin")
        imports = summarize("import")
        result[account_id] = {
            "origin_families": origins,
            "imported_families": imports,
            "origin_family_count": len(origins),
            "imported_family_count": len(imports),
            "total_family_observations": len(origins) + len(imports),
        }
    return result


def strategy_role_lineage(
    strategy: dict[str, Any],
    role_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Attach direct chronology to role claims without altering warehouse rows."""
    hypothesis_type = _text(strategy.get("hypothesis_type"))
    account_ids: list[str] = []
    if hypothesis_type in {
        "account_origin_exploration",
        "account_reuse_receiver",
        "account_reuse_amplification",
    }:
        account_ids = [_text(strategy.get("account_id"))]
    elif hypothesis_type == "operator_explore_propagate_model":
        summary = strategy.get("evidence_summary")
        if not isinstance(summary, dict):
            summary = _json(strategy.get("evidence_summary_json"), {})
        for key in ("origin_accounts", "receiver_accounts"):
            account_ids.extend(_text(item) for item in summary.get(key, []))
    else:
        return None

    account_ids = sorted(set(account_id for account_id in account_ids if account_id))
    return {
        "accounts": [
            {"account_id": account_id, **role_index.get(account_id, empty_role_lineage())}
            for account_id in account_ids
        ]
    }


# These are validation-oriented application exercises, not assertions about an
# operator's internal process.  No invented thresholds or causal win rates.
_STEPS = (
    (
        "explore",
        "Explore",
        "operator_explore_propagate_model",
        "Log new concepts and their first observed accounts. Treat the apparent "
        "origin account as a research lead, not a proven testing assignment.",
        "Check origin/import family examples and look for unobserved earlier posts.",
    ),
    (
        "select",
        "Select for reuse",
        "selective_cross_account_reuse_model",
        "Compare one-off and reused concepts before setting your own selection "
        "criteria. Do not infer that the operator selected only winning posts.",
        "Inspect the full repeated-family denominator and losing reuses.",
    ),
    (
        "adapt",
        "Adapt execution",
        "preserve_core_vary_execution",
        "Compare the original and receiving executions side by side. Test "
        "preserving the observed core while changing execution; do not copy media.",
        "Open original/receiving posts and inspect preserved, changed, and unknown dimensions.",
    ),
    (
        "distribute",
        "Distribute across accounts",
        "operator_explore_propagate_model",
        "Pilot cross-account reuse with explicit family and account lineage. "
        "Record every receiving execution; a receiver is not proven to be a scaling account.",
        "Check observed origin-to-receiver chronology and alternative explanations.",
    ),
    (
        "measure",
        "Measure & decide",
        None,
        "For your own pilot, compare origin and receiving posts to their respective "
        "account baselines; record failed as well as successful adaptations.",
        "This is a validation protocol, not a claimed observation of the operator's workflow.",
    ),
)


def _knowledge_for_source(
    knowledge: list[dict[str, Any]],
    hypothesis_id: str,
    operator_id: str,
) -> list[dict[str, Any]]:
    matches = []
    for row in knowledge:
        if operator_id and _text(row.get("operator_id")) != operator_id:
            continue
        if _text(row.get("review_source_type")) == "hypothesis":
            if _text(row.get("review_source_id")) == hypothesis_id:
                matches.append(row)
        elif (
            _text(row.get("source_type")) == "hypothesis"
            and hypothesis_id in _json(row.get("source_ids_json"), [])
        ):
            matches.append(row)
    return matches


def _trust_for_source(knowledge_rows: list[dict[str, Any]]) -> str:
    statuses = {_text(row.get("knowledge_status")) for row in knowledge_rows}
    # Any explicit block overrides automatic promotion or other derived items.
    for blocked in ("rejected", "hold"):
        if blocked in statuses:
            return blocked
    if "approved" in statuses:
        return "approved"
    if "promoted" in statuses:
        return "auto_promoted"
    if "review_candidate" in statuses:
        return "review_candidate"
    return "hypothesis_only"


def hypothesis_trust_status(
    knowledge: list[dict[str, Any]],
    hypothesis_id: str,
    operator_id: str,
) -> str:
    """Scope-aware trust state used by Research Brief and Playbook alike."""
    return _trust_for_source(_knowledge_for_source(knowledge, hypothesis_id, operator_id))


def build_provisional_playbook(
    strategies: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
    *,
    operator_id: str,
) -> dict[str, Any]:
    """A transparent reviewable decision aid, never trusted knowledge by default."""
    source_map: dict[str, list[dict[str, Any]]] = {}
    for row in strategies:
        if _text(row.get("operator_id")) == operator_id:
            source_map.setdefault(_text(row.get("hypothesis_type")), []).append(row)
    for rows in source_map.values():
        rows.sort(
            key=lambda row: (
                -(float(row.get("confidence_score") or 0.0)),
                _text(row.get("hypothesis_id")),
            )
        )

    steps: list[dict[str, Any]] = []
    for key, title, hypothesis_type, exercise, verify in _STEPS:
        source = (
            source_map.get(hypothesis_type, [None])[0]
            if hypothesis_type is not None
            else None
        )
        source_id = _text(source.get("hypothesis_id")) if source else None
        source_knowledge = (
            _knowledge_for_source(knowledge, source_id, operator_id)
            if source_id
            else []
        )
        trust = (
            _trust_for_source(source_knowledge)
            if source
            else ("validation_protocol" if hypothesis_type is None else "no_evidence")
        )
        blocked = trust in {"rejected", "hold"}
        summary = source.get("evidence_summary") if source else {}
        if source and not isinstance(summary, dict):
            summary = _json(source.get("evidence_summary_json"), {})
        alternatives = source.get("alternative_explanations") if source else []
        if source and not isinstance(alternatives, list):
            alternatives = _json(source.get("alternative_explanations_json"), [])
        counter = source.get("counter_evidence") if source else {}
        if source and not isinstance(counter, dict):
            counter = _json(source.get("counter_evidence_json"), {})
        steps.append(
            {
                "key": key,
                "title": title,
                "source_hypothesis_id": source_id,
                "trust_status": trust,
                "confidence_score": (
                    source.get("confidence_score") if source else None
                ),
                "observation": (
                    source.get("claim") if source and not blocked else None
                ),
                "application_exercise": (
                    exercise if not blocked and trust != "no_evidence" else None
                ),
                "verification_question": verify,
                "evidence_summary": summary if not blocked else {},
                "alternative_explanations": alternatives if not blocked else [],
                "counter_evidence": counter if not blocked else {},
                "source_knowledge_ids": [
                    row.get("knowledge_id") for row in source_knowledge
                ],
                "not_an_operator_claim": hypothesis_type is None,
            }
        )

    approved_sources = sum(
        step["trust_status"] == "approved"
        for step in steps
        if step["source_hypothesis_id"]
    )
    observational_steps = sum(bool(step["source_hypothesis_id"]) for step in steps)
    trusted_playbooks = [
        {
            "knowledge_id": row.get("knowledge_id"),
            "title": row.get("title"),
            "status": row.get("knowledge_status"),
        }
        for row in knowledge
        if _text(row.get("operator_id")) == operator_id
        and _text(row.get("knowledge_type")) == "playbook"
        and _text(row.get("knowledge_status")) in {"approved", "promoted"}
    ]
    return {
        "status": (
            "human_reviewed"
            if observational_steps == 4 and approved_sources == 4
            else "research_draft"
        ),
        "operator_id": operator_id,
        "title": "Operator Playbook — evidence-backed research draft",
        "steps": steps,
        "approved_source_steps": approved_sources,
        "observational_source_steps": observational_steps,
        "trusted_catalog_playbooks": trusted_playbooks,
        "guardrails": [
            "Hypothesis confidence is not human approval.",
            "Auto-promoted knowledge is not a human-validated operating rule.",
            "Chronological cross-account reuse does not prove test → scale or causation.",
            "Application exercises are proposals to validate in your system, not proven wins.",
            "Held/rejected sources are never presented as actionable guidance.",
        ],
    }
