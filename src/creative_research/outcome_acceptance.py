"""Acceptance checks for materialized Operator Intelligence Lab research outcomes.

This checks observable evidence lineage and trust boundaries, not media playback,
human correctness of semantic clustering, or a 5–10 minute usability session.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


ROLE_TYPES = {
    "account_origin_exploration",
    "account_reuse_receiver",
    "account_reuse_amplification",
    "operator_explore_propagate_model",
}


def audit_outcome(
    *,
    lab: dict[str, Any],
    families: dict[str, Any],
    strategies: dict[str, Any],
    knowledge: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checked = Counter()

    def issue(code: str, message: str, *, fatal: bool = True) -> None:
        target = failures if fatal else warnings
        if not any(item["code"] == code and item["message"] == message for item in target):
            target.append({"code": code, "message": message})

    posts = {
        str(row.get("post_uid")): row
        for row in evidence.get("posts", [])
        if row.get("post_uid")
    }
    family_rows = families.get("families", [])
    family_by_id = {
        str(row.get("family_id")): row
        for row in family_rows if row.get("family_id")
    }
    strategy_by_id = {
        str(row.get("hypothesis_id")): row
        for row in strategies.get("strategies", [])
        if row.get("hypothesis_id")
    }
    knowledge_rows = knowledge.get("knowledge", [])
    brief = lab.get("research_brief", {})
    stats = brief.get("stats", {})
    repeated = [row for row in family_rows if (row.get("member_count") or 0) > 1]
    cross_repeated = [row for row in repeated if bool(row.get("cross_account"))]

    for key, expected in (
        ("families", len(family_rows)),
        ("repeated_families", len(repeated)),
        ("cross_account_repeated_families", len(cross_repeated)),
    ):
        checked["brief_totals"] += 1
        if stats.get(key) != expected:
            issue("brief_count_mismatch", f"{key}: displayed {stats.get(key)}, actual {expected}")
    if stats.get("posts") != len(posts):
        issue("brief_count_mismatch", "Post count does not match canonical evidence.")
    if not family_rows or not posts:
        issue("empty_research", "No canonical posts or families available for research validation.")

    blocked_sources = {
        str(row.get("review_source_id"))
        for row in knowledge_rows
        if row.get("review_source_type") == "hypothesis"
        and row.get("knowledge_status") in {"hold", "rejected"}
    }
    hero_id = (brief.get("hero") or {}).get("hypothesis_id")
    if str(hero_id) in blocked_sources:
        issue("blocked_featured_claim", "The Research Brief hero uses held/rejected evidence.")
    for finding in brief.get("key_findings", []):
        if str(finding.get("hypothesis_id")) in blocked_sources:
            issue(
                "blocked_featured_claim",
                f"Featured hypothesis {finding.get('hypothesis_id')} is held/rejected.",
            )
    if hero_id and str(hero_id) not in strategy_by_id:
        issue("untraceable_hero", f"Research Brief source {hero_id} was not materialized.")
    checked["hero"] = int(bool(hero_id))

    def check_flow(
        flow: dict[str, Any],
        family_id: str,
        owner: str,
        direction: str,
    ) -> None:
        checked["flow_pairs"] += 1
        if str(flow.get("family_id")) != family_id:
            issue("flow_family_mismatch", f"{owner}: role family and flow IDs differ.")
        family = family_by_id.get(family_id)
        if family is None:
            issue("missing_flow_family", f"{owner}: family {family_id} does not exist.")
            return
        member_ids = {
            str(row.get("post_uid")) for row in family.get("members", [])
        }
        for prefix, account_field in (
            ("origin", "origin_account_id"),
            ("target", "target_account_id"),
        ):
            post_id = str(flow.get(prefix + "_post_uid") or "")
            post = posts.get(post_id)
            if post is None:
                issue("missing_flow_post", f"{family_id}: {prefix} post {post_id!r} not found.")
                continue
            if post_id not in member_ids:
                issue("missing_family_member", f"{family_id}: {prefix} post not in family members.")
            if str(post.get("account_id")) != str(flow.get(account_field)):
                issue("flow_account_mismatch", f"{family_id}: {prefix} post account does not match flow.")
            if not post.get("url"):
                issue("missing_source_url", f"{family_id}: {prefix} post has no original source URL.")
        expected_account_field = "origin_account_id" if direction == "origin" else "target_account_id"
        if str(flow.get(expected_account_field)) != owner:
            issue("flow_direction_mismatch", f"{family_id}: wrong account for {direction} evidence.")

    node_by_id = {}
    for account in lab.get("account_network", {}).get("nodes", []):
        account_id = str(account.get("account_id") or "")
        if not account_id:
            issue("missing_account_id", "Account network contains a node without an account ID.")
            continue
        node_by_id[account_id] = account
        lineage = account.get("role_lineage")
        checked["account_roles"] += 1
        if not isinstance(lineage, dict):
            issue("missing_role_lineage", f"{account_id}: account has no direct role lineage.")
            continue

        counted = 0
        for direction, group_key, count_key in (
            ("origin", "origin_families", "origin_family_count"),
            ("import", "imported_families", "imported_family_count"),
        ):
            groups = lineage.get(group_key, [])
            unique_ids = {str(group.get("family_id")) for group in groups}
            if len(unique_ids) != len(groups):
                issue("duplicate_role_family", f"{account_id}: repeated {direction} family.")
            if lineage.get(count_key) != len(groups):
                issue("role_count_mismatch", f"{account_id}: wrong {direction} family count.")
            counted += len(groups)
            for group in groups:
                family_id = str(group.get("family_id") or "")
                flows = group.get("flows", [])
                if not flows:
                    issue("missing_role_flow", f"{account_id}: {family_id} has no post-pair flow.")
                for flow in flows:
                    check_flow(flow, family_id, account_id, direction)

        observed = account.get("flow_observations")
        if counted != observed or counted != lineage.get("total_family_observations"):
            issue(
                "role_denominator_mismatch",
                f"{account_id}: traceable {counted} family observations, role summary {observed}.",
            )
        if account.get("lineage_matches_summary") is not True:
            issue("role_denominator_mismatch", f"{account_id}: role lineage is not reconciled.")

    for strategy in strategy_by_id.values():
        if strategy.get("hypothesis_type") not in ROLE_TYPES:
            continue
        checked["role_hypotheses"] += 1
        detail = strategy.get("flow_evidence") or {}
        account_details = detail.get("accounts", [])
        if not account_details:
            issue(
                "hypothesis_missing_direct_flows",
                f"{strategy['hypothesis_id']}: role claim has no linked account families.",
            )
        for entry in account_details:
            account_id = str(entry.get("account_id") or "")
            if account_id not in node_by_id:
                issue("hypothesis_unknown_account", f"{strategy['hypothesis_id']}: {account_id}.")
            else:
                actual = node_by_id[account_id].get("role_lineage") or {}
                for direction in ("origin_families", "imported_families"):
                    expected_ids = {
                        str(group.get("family_id"))
                        for group in actual.get(direction, [])
                    }
                    linked_ids = {
                        str(group.get("family_id"))
                        for group in entry.get(direction, [])
                    }
                    if linked_ids != expected_ids:
                        issue(
                            "hypothesis_flow_mismatch",
                            f"{strategy['hypothesis_id']}: {account_id} {direction} differs from account lineage.",
                        )
            if entry.get("total_family_observations", 0) < 1:
                issue(
                    "hypothesis_missing_direct_flows",
                    f"{strategy['hypothesis_id']}: {account_id} has no concrete flow.",
                )

    core_models = {
        "selective_cross_account_reuse_model",
        "operator_explore_propagate_model",
    }
    if not any(
        row.get("hypothesis_type") in core_models
        for row in strategy_by_id.values()
    ):
        issue(
            "operating_model_not_established",
            "No high-level operator operating model has been emitted.",
            fatal=False,
        )

    playbook = lab.get("playbook")
    if not isinstance(playbook, dict):
        issue("missing_playbook", "The Lab lacks a provisional decision playbook.")
        playbook = {}
    steps = playbook.get("steps", [])
    if {step.get("key") for step in steps} != {
        "explore", "select", "adapt", "distribute", "measure"
    }:
        issue("missing_playbook_step", "Decision protocol must cover all five steps.")
    approved_step_count = 0
    for step in steps:
        checked["playbook_steps"] += 1
        trust = step.get("trust_status")
        source = step.get("source_hypothesis_id")
        if source and str(source) not in strategy_by_id:
            issue("untraceable_playbook_source", f"{step.get('key')}: unknown hypothesis {source}.")
        if trust in {"rejected", "hold"}:
            if step.get("application_exercise") or step.get("observation"):
                issue("blocked_guidance_leak", f"{step.get('key')}: blocked source is actionable.")
        if trust == "approved":
            approved_step_count += 1
            matching = [
                row for row in knowledge_rows
                if row.get("review_source_type") == "hypothesis"
                and str(row.get("review_source_id")) == str(source)
            ]
            if not any(row.get("knowledge_status") == "approved" for row in matching):
                issue("unearned_review_status", f"{step.get('key')}: approval has no knowledge source.")
        if step.get("key") == "measure" and (
            step.get("not_an_operator_claim") is not True or source is not None
        ):
            issue("protocol_mislabeled_as_observation", "Measurement method claimed as operator evidence.")

    if playbook.get("approved_source_steps") != approved_step_count:
        issue("approval_count_mismatch", "Playbook source approvals disagree with steps.")

    for row in knowledge.get("active", []):
        if row.get("knowledge_status") not in {"approved", "promoted"}:
            issue("blocked_active_knowledge", "Held/rejected/unreviewed knowledge appears active.")

    catalog_playbooks = [
        row for row in knowledge_rows if row.get("knowledge_type") == "playbook"
        and row.get("knowledge_status") in {"approved", "promoted"}
    ]
    if not catalog_playbooks:
        issue(
            "no_trusted_catalog_playbook",
            "No approved/auto-promoted catalog playbook; the Lab draft remains provisional.",
            fatal=False,
        )
    if approved_step_count < 4:
        issue(
            "human_review_pending",
            f"Only {approved_step_count}/4 observational playbook steps have approved sources.",
            fatal=False,
        )
    issue(
        "manual_usability_unverified",
        "Visual media playback and the 5–10 minute nontechnical user test require a real Lab session.",
        fatal=False,
    )
    return {
        "schema_version": "research-outcome-audit-v1",
        "status": "fail" if failures else (
            "ready_for_usability_test"
            if catalog_playbooks and approved_step_count == 4
            else "conditional_pass"
        ),
        "counts": dict(checked),
        "failures": failures,
        "warnings": warnings,
        "scope": (
            "Materialized claims, family/post lineage, review boundaries, and "
            "decision guidance only. Does not validate semantics or media playback."
        ),
    }
