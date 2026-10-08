"""Machine-owned research classification: observed, inferred, unknown.

Nothing here represents a human approval or asserts undocumented operator
intent. Multilingual creative families are checked using normalized Vision
signatures and clustering lineage, not by outsourcing truth to a researcher.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

RESEARCH_SCHEMA_VERSION = "research-intelligence-v1"
# These are diagnostic thresholds, NOT truth/identity verification cutoffs.
LOW_MATCH_DIAGNOSTIC = 0.67
def _json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            pass
    return {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if 0 <= number <= 1 else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    """Comparable language-aware Vision labels, not invented translations."""
    return " ".join(re.findall(r"\w+", _text(value).casefold(), flags=re.UNICODE))


def family_diagnostics(
    *,
    families: list[dict[str, Any]],
    members: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    creative_analysis: list[dict[str, Any]],
) -> dict[str, Any]:
    """No approvals; emit reproducible machine QA and unresolved uncertainty.

    Cross-language claims are checked against already normalized Vision fields
    and the family's clustering match evidence. Direct content translation
    accuracy is NOT certified without an independent model/visual judge.
    """
    posts_by_id = {str(r["post_uid"]): r for r in posts if r.get("post_uid")}
    analysis_by_id = {
        str(r["post_uid"]): r for r in creative_analysis if r.get("post_uid")
    }
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for member in members:
        if member.get("family_id"):
            by_family[str(member["family_id"])].append(member)
    diagnostics = []
    counts: Counter[str] = Counter()
    for family in families:
        member_count = int(family.get("member_count") or 0)
        if member_count < 2:
            continue
        family_id = str(family.get("family_id") or "")
        group = by_family.get(family_id, [])
        evidence_posts = [
            str(row.get("post_uid") or "") for row in group
        ]
        issues: list[str] = []
        if (
            member_count != len(group)
            or not evidence_posts
            or len(set(evidence_posts)) != len(evidence_posts)
        ):
            issues.append("family_membership_integrity")
        missing_posts = [
            uid for uid in evidence_posts if uid not in posts_by_id
        ]
        if missing_posts:
            issues.append("orphan_post_evidence")

        language_codes = {
            _text(analysis_by_id.get(uid, {}).get("primary_language_code")).casefold()
            for uid in evidence_posts
            if analysis_by_id.get(uid, {}).get("primary_language_code")
        }
        multilingual = len(language_codes) > 1
        if multilingual:
            counts["multilingual_families"] += 1

        # Reuse Vision's language-normalized semantic fields: compare actual
        # analysis labels rather than translating by string replacement.
        core_angle = _normalized(family.get("core_angle"))
        core_topic = _normalized(family.get("core_topic"))
        angle_values = {
            _normalized(analysis_by_id.get(uid, {}).get("content_angle"))
            for uid in evidence_posts
            if analysis_by_id.get(uid, {}).get("content_angle")
        }
        topic_values = {
            _normalized(analysis_by_id.get(uid, {}).get("topic"))
            for uid in evidence_posts
            if analysis_by_id.get(uid, {}).get("topic")
        }
        # Mismatches are a QA signal, not grounds for automatically splitting.
        if core_angle and angle_values and core_angle not in angle_values:
            issues.append("core_angle_not_represented")
        if core_topic and topic_values and core_topic not in topic_values:
            issues.append("core_topic_not_represented")

        match_scores = [
            score for row in group
            if (score := _number(row.get("match_score_to_origin"))) is not None
        ]
        if match_scores and min(match_scores) < LOW_MATCH_DIAGNOSTIC:
            issues.append("low_anchor_match")
        if not match_scores and member_count > 1:
            issues.append("match_scores_unavailable")
        if multilingual:
            translation_support = any(
                "translat" in _text(row.get("match_anchor_gate")).casefold()
                or "translat" in json.dumps(_json(row.get("match_reason_json"))).casefold()
                for row in group
            )
            if not translation_support:
                issues.append("multilingual_identity_needs_independent_check")

        status = (
            "integrity_gap" if any(x in issues for x in (
                "family_membership_integrity", "orphan_post_evidence"
            ))
            else "semantic_uncertain" if issues
            else "structurally_consistent_candidate"
        )
        counts[status] += 1
        diagnostics.append({
            "family_id": family_id,
            "member_count": member_count,
            "accounts_count": int(family.get("accounts_count") or 0),
            "multilingual": multilingual,
            "languages": sorted(language_codes),
            "automated_state": status,
            "flags": sorted(set(issues)),
            "sample_post_uids": evidence_posts[:8],
            "min_anchor_match": min(match_scores) if match_scores else None,
            "quality_basis": (
                "Vision-normalized topic/angle, language and family "
                "match lineage; not direct inspection of raw media."
            ),
            "no_human_approval_required": True,
        })
    diagnostics.sort(key=lambda row: (
        0 if row["automated_state"] == "integrity_gap"
        else 1 if row["automated_state"] == "semantic_uncertain"
        else 2,
        -row["member_count"], row["family_id"],
    ))
    return {
        "counts": {
            "repeated_families_checked": len(diagnostics),
            "multilingual_families": counts["multilingual_families"],
            "integrity_gaps": counts["integrity_gap"],
            "semantic_uncertain": counts["semantic_uncertain"],
            "structurally_consistent_candidates": counts[
                "structurally_consistent_candidate"
            ],
        },
        "items": diagnostics,
        "method": (
            "Deterministic cross-language diagnostics. Semantic confidence "
            "remains a candidate, not proof of equivalent core meaning."
        ),
        "human_review_required": False,
    }


def build_research_intelligence(
    *,
    operator_id: str,
    stats: dict[str, Any],
    strategies: list[dict[str, Any]],
    families: list[dict[str, Any]],
    members: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    creative_analysis: list[dict[str, Any]],
    playbook_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify claims by epistemic type, not by user Approval status."""
    diagnostics = family_diagnostics(
        families=families, members=members, posts=posts,
        creative_analysis=creative_analysis,
    )
    if stats.get("posts") is not None and int(stats["posts"]) != len(posts):
        raise ValueError("research_stats_posts_mismatch")
    if stats.get("families") is not None and int(stats["families"]) != len(families):
        raise ValueError("research_stats_families_mismatch")

    observed: list[dict[str, Any]] = [{
        "id": "observed-coverage",
        "title": "Observed public research coverage",
        "statement": (
            f"{stats.get('posts', 0)} posts across {stats.get('accounts', 0)} "
            f"operator-declared accounts were included in this snapshot."
        ),
        "basis": "canonical_post_and_account_counts",
        "metrics": {
            "posts": stats.get("posts", 0),
            "accounts": stats.get("accounts", 0),
        },
        "limitations": "Sample coverage may omit deleted/private/unretrieved posts.",
    }]
    repeated = int(stats.get("repeated_families") or 0)
    cross = int(stats.get("cross_account_repeated_families") or 0)
    if repeated:
        observed.append({
            "id": "observed-reuse",
            "title": "Observed selective family recurrence",
            "statement": (
                f"{repeated} of {len(families)} candidate creative families "
                f"contain multiple executions; {cross} of those recur "
                "across operator-declared accounts."
            ),
            "basis": "creative_family_counts",
            "metrics": {
                "repeated_families": repeated,
                "cross_account_repeated_families": cross,
                "all_families": len(families),
            },
            "limitations": (
                "Family identity is algorithmic; chronology cannot prove "
                "intentional copying or a scaling workflow."
            ),
        })
    if int(stats.get("propagation_events") or 0) > 0:
        observed.append({
            "id": "observed-chronology",
            "title": "Cross-account chronology",
            "statement": (
                f"{stats['propagation_events']} later account appearances "
                "were observed inside matched creative families."
            ),
            "basis": "cross_account_propagation_rows",
            "metrics": {"events": stats["propagation_events"]},
            "limitations": "First observed is not a verified causal origin.",
        })

    inferred: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(
        strategies,
        key=lambda item: -float(item.get("confidence_score") or 0.0),
    ):
        kind = _text(row.get("hypothesis_type"))
        if kind == "temporal_strategy_shift" or not row.get("hypothesis_id"):
            continue
        sid = str(row["hypothesis_id"])
        if sid in seen:
            continue
        seen.add(sid)
        inferred.append({
            "id": sid,
            "title": row.get("title") or kind.replace("_", " "),
            "claim": row.get("claim"),
            "hypothesis_type": kind,
            "confidence_score": row.get("confidence_score"),
            "scope_type": row.get("scope_type"),
            "account_id": row.get("account_id"),
            "support": _json(row.get("evidence_summary") or row.get("evidence_summary_json")),
            "counter_evidence": _json(
                row.get("counter_evidence") or row.get("counter_evidence_json")
            ),
            "alternatives": _json(
                row.get("alternative_explanations")
                or row.get("alternative_explanations_json")
            ),
            "interpretation_not_internal_fact": True,
            "evidence_ref": f"hypothesis:{sid}",
        })
    unknown = [
        {
            "id": "unknown-operator-intent",
            "title": "Internal testing and scaling decisions",
            "statement": (
                "Public posts cannot establish which account was deliberately "
                "assigned to test, when a manager decided to scale, or why."
            ),
            "reason": "Internal directives are not public research evidence.",
        },
        {
            "id": "unknown-causation",
            "title": "Why an execution spread or performed differently",
            "statement": (
                "Matched posts and timing alone do not establish causal "
                "distribution paths or winning-post selection rules."
            ),
            "reason": "Observational data without interventions/controls.",
        },
        {
            "id": "unknown-outcomes",
            "title": "Whether the operator's tactics will work for you",
            "statement": (
                "Historical public views cannot prove transferability, "
                "conversion, or future success for your accounts."
            ),
            "reason": "Requires new first-party experiments and outcome tracking.",
        },
    ]
    # Actionable tests are available without a human truth-certification gate.
    experiments: list[dict[str, Any]] = []
    for step in playbook_steps:
        key = _text(step.get("key"))
        hypothesis_id = _text(step.get("source_hypothesis_id"))
        available = bool(hypothesis_id and any(
            row.get("hypothesis_id") == hypothesis_id for row in strategies
        ))
        experiments.append({
            "key": key,
            "title": step.get("title") or key,
            "application_exercise": (
                step.get("application_exercise")
                or "Design a small validation experiment; collect your own results."
            ),
            "verification_question": step.get("verification_question"),
            "related_hypothesis_id": hypothesis_id or None,
            "basis": "inferred" if available else "method_only",
            "evidence_confidence": step.get("confidence_score") if available else None,
            "experiment_not_proven": True,
            "suggested_metric": (
                "Account-relative views percentile, observed on your own posts"
            ),
            "stop_or_recheck": (
                "Review both winners and losers after a predeclared sample; "
                "do not infer success from a single execution."
            ),
        })
    return {
        "schema_version": RESEARCH_SCHEMA_VERSION,
        "operator_id": operator_id,
        "no_human_truth_approval_required": True,
        "classification_method": (
            "Deterministic observations vs bounded strategy inference vs "
            "questions unidentifiable from public data."
        ),
        "observed": observed,
        "inferred": inferred,
        "unknown": unknown,
        "family_quality": diagnostics,
        "experiment_candidates": experiments,
        "counts": {
            "observed": len(observed),
            "inferred": len(inferred),
            "unknown": len(unknown),
            "experiment_candidates": len(experiments),
        },
        "limits": [
            "Account grouping is user-declared before scrape, not independently verified.",
            "Multilingual matches remain auditable candidate families; matching is automated.",
            "A high model confidence does not become an observed fact.",
            "Only first-party experiments can validate an application outcome.",
        ],
    }
