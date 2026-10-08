"""Evidence-linked, team-facing creator production plan.

Consumes already-materialized public operator research. It does NOT fetch
Pinterest, copy source media, grant usage rights, invent sound metadata, infer
internal operator intent, or claim an experiment is proven effective.
"""
from __future__ import annotations

import hashlib
import statistics
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from creative_research.production_fields import (
    _text, _slug, _num, _median, _clean_copy, _read_json, _pct,
)
from creative_research.production_source_bank import enrich_production_kit_from_raw
from creative_research.production_contracts import (
    SCHEMA_VERSION, DEFAULT_RECIPES, DEFAULT_DAYS, MAX_RECIPES, MAX_DAYS,
)
from creative_research.production_quality import audit_production_kit
from creative_research.production_handoff import (
    production_kit_artifacts, write_production_kit,
)
from creative_research.production_copy import (
    _creative_kind,
    _editorial_spec,
    _visual_query,
    _draft_for_role,
    _VARIANT_HOOK_VI,
    _VARIANT_SUBTYPE_HOOK_VI,
)




def _family_members(family: dict[str, Any], posts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    members = family.get("members") or []
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for member in members:
        uid = _text(member.get("post_uid"))
        if uid and uid in posts and uid not in seen:
            seen.add(uid)
            unique.append(posts[uid])
    if not unique:
        uid = _text(family.get("representative_post_uid") or family.get("family_origin_post_uid"))
        if uid in posts:
            unique.append(posts[uid])
    return unique


def _rank_family(fam: dict[str, Any], members: list[dict[str, Any]]) -> float:
    pct = [_pct(p) for p in members]
    pct = [v for v in pct if v is not None]
    save = [(_num(p.get("save_rate")) or 0) for p in members]
    coverage = len({p.get("account_id") for p in members})
    # Ranking heuristic for editorial inspection, NOT probability of success.
    return round(
        1.15 * min(coverage, 5) + 0.8 * min(len(members), 5)
        + 3.0 * (statistics.median(pct) if pct else 0)
        + 0.4 * (max(pct) if pct else 0)
        + 4.0 * (statistics.median(save) if save else 0),
        4,
    )


def _family_signature(fam: dict[str, Any], members: list[dict[str, Any]]) -> str:
    example = (members[0].get("creative") or {}) if members else {}
    topic = _slug(fam.get("core_topic") or example.get("topic"))
    hook = _slug(fam.get("core_hook_formula") or example.get("hook_replicable_formula"))
    return (topic[:64] + "|" + hook[:90]).strip("|")


def _select_families(
    families: list[dict[str, Any]],
    post_map: dict[str, dict[str, Any]],
    limit: int,
) -> list[tuple[dict[str, Any], list[dict[str, Any]], float]]:
    candidates: list[tuple[dict[str, Any], list[dict[str, Any]], float]] = []
    for fam in families:
        members = _family_members(fam, post_map)
        if not members:
            continue
        if not any((p.get("sequence") or []) for p in members):
            continue
        candidates.append((fam, members, _rank_family(fam, members)))
    candidates.sort(key=lambda item: (
        -int(len(item[1]) >= 2),
        -item[2],
        _text(item[0].get("family_id")),
    ))
    # Keep most recipes grounded in repeated patterns, plus a few single-post
    # explorations with high observed percentile; never call the latter validated.
    selected: list[tuple[dict[str, Any], list[dict[str, Any]], float]] = []
    used: set[str] = set()
    used_signature: set[str] = set()
    repeated_target = max(1, round(limit * 0.70))
    for pass_single in (False, True):
        for fam, members, score in candidates:
            if (len(members) == 1) != pass_single:
                continue
            if len(selected) >= limit:
                break
            if not pass_single and len(selected) >= repeated_target:
                break
            fid = _text(fam.get("family_id"))
            sig = _family_signature(fam, members)
            if fid in used or (sig and sig in used_signature):
                continue
            selected.append((fam, members, score))
            used.add(fid)
            if sig:
                used_signature.add(sig)
    # If there were few singletons, use more distinct repeated examples.
    if len(selected) < limit:
        for fam, members, score in candidates:
            fid = _text(fam.get("family_id"))
            sig = _family_signature(fam, members)
            if len(selected) >= limit:
                break
            if fid not in used and (not sig or sig not in used_signature):
                selected.append((fam, members, score))
                used.add(fid)
                if sig:
                    used_signature.add(sig)
    return selected


def _reference_posts(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in members:
        creative = post.get("creative") or {}
        rows.append({
            "post_uid": post["post_uid"],
            "account": post.get("account"),
            "account_id": post.get("account_id"),
            "post_id": post.get("post_id"),
            "url": post.get("url"),
            "views": post.get("views"),
            "account_relative_views_percentile": _pct(post),
            "saves": post.get("saves"),
            "created_at": post.get("created_at"),
            "hook_reference": _clean_copy(creative.get("hook_text")),
        })
    return rows


def _candidate_false_splits(
    families: list[dict[str, Any]], post_map: dict[str, dict[str, Any]],
    max_pairs: int = 50,
) -> list[dict[str, Any]]:
    by_hook: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fam in families:
        if int(fam.get("member_count") or 0) != 1:
            continue
        uid = _text(fam.get("family_origin_post_uid") or fam.get("representative_post_uid"))
        post = post_map.get(uid)
        hook = _slug(fam.get("core_hook_text") or (post or {}).get("creative", {}).get("hook_text"))
        if hook and post and len(hook) >= 25:
            by_hook[hook].append(fam)
    matches: list[dict[str, Any]] = []
    for hook, group in sorted(by_hook.items()):
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda f: str(f.get("family_id")))[:20]
        for a, b in combinations(group, 2):
            if len(matches) >= max_pairs:
                return matches
            pa = post_map.get(_text(a.get("family_origin_post_uid")))
            pb = post_map.get(_text(b.get("family_origin_post_uid")))
            if not pa or not pb or pa.get("account_id") == pb.get("account_id"):
                continue
            aa, bb = pa.get("creative") or {}, pb.get("creative") or {}
            shared_product = _slug(aa.get("product_family")) == _slug(bb.get("product_family"))
            if not shared_product:
                continue
            role_a = [_slug(s.get("role")) for s in pa.get("sequence") or []]
            role_b = [_slug(s.get("role")) for s in pb.get("sequence") or []]
            if not role_a or role_a != role_b:
                continue
            matches.append({
                "family_a": a.get("family_id"),
                "family_b": b.get("family_id"),
                "post_a": pa["post_uid"],
                "post_b": pb["post_uid"],
                "url_a": pa.get("url"), "url_b": pb.get("url"),
                "accounts": [pa.get("account"), pb.get("account")],
                "shared_hook_reference": hook[:180],
                "matching_sequence_roles": role_a,
                "shared_product_family": aa.get("product_family"),
                "finding": "possible_false_split_needs_semantic_or_visual_check",
                "validated_same_concept": False,
            })
    return matches


def _blueprints(
    accounts: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    niche_counts = Counter(
        _slug((p.get("creative") or {}).get("audience_segment"))
        for p in posts
        if p.get("creative")
    )
    audience = [x for x, n in niche_counts.most_common(7) if x and n >= 5]
    if not audience:
        audience = ["student"]
    observed = sorted(
        accounts, key=lambda a: -(int(a.get("observed_posts") or 0))
    )[:4]
    source_account_refs = [{
        "account_id": a.get("account_id"), "handle": a.get("account"),
        "observed_posts": a.get("observed_posts"),
        "median_views": (a.get("performance_baseline") or {}).get("median_views"),
        "median_gap_hours": (a.get("cadence_summary") or {}).get("median_gap_hours"),
        "top_posting_hours_utc": _read_json(
            (a.get("cadence_summary") or {}).get("top_posting_hours_json")
        ) or [],
    } for a in observed]
    return [
        {
            "slot_id": "PILOT-A",
            "account_type": "owned_original_content",
            "positioning": "Mẹo học và lịch học thực tế cho sinh viên",
            "audience": "Sinh viên muốn học có kế hoạch",
            "suggested_handle_pattern": "study.<topic>.<your_brand> (verify availability)",
            "bio_draft": "Lịch học dễ áp dụng • Mẹo ghi nhớ • Chia sẻ trải nghiệm học thật",
            "avatar_brief": "Original minimal study-themed icon; do not mimic the operator identity",
            "content_pillars": ["study schedules", "study methods", "exam planning"],
            "proposed_cadence": "1 post every two days during pilot",
            "proposed_local_time": "19:00",
            "time_zone": "Asia/Ho_Chi_Minh",
            "reference_audience_labels": audience[:4],
            "source_account_observations": source_account_refs[:2],
            "setup_checklist": [
                "Create and verify a unique account that you own",
                "Choose a consistent audience and language",
                "Use a brand-owned avatar and authentic bio",
                "Enable appropriate account security and disclose promotions",
                "Prepare a tracking sheet and original licensed content",
            ],
            "evidence_boundary": "Pilot account strategy, NOT a proven operator internal role.",
        },
        {
            "slot_id": "PILOT-B",
            "account_type": "owned_original_content",
            "positioning": "Ôn thi, ghi chú và thử các phương pháp ghi nhớ",
            "audience": "Người cần ôn tập và ghi chép có hệ thống",
            "suggested_handle_pattern": "notes.<topic>.<your_brand> (verify availability)",
            "bio_draft": "Ôn thi có hệ thống • Ghi chú • Thử nghiệm phương pháp học",
            "avatar_brief": "Original notebook/flashcard brand mark with documented source",
            "content_pillars": ["note taking", "exam prep", "study tools"],
            "proposed_cadence": "1 post every two days during pilot",
            "proposed_local_time": "21:00",
            "time_zone": "Asia/Ho_Chi_Minh",
            "reference_audience_labels": audience[:4],
            "source_account_observations": source_account_refs[2:4],
            "setup_checklist": [
                "Verify unique handle and own the account",
                "Choose one audience and one voice",
                "Set avatar and bio with owned creative",
                "Prepare a repeatable original visual template",
                "Log publication and outcomes consistently",
            ],
            "evidence_boundary": "Pilot segmentation is a proposal; hours are not validated best times.",
        },
    ]


def _tactical_observations(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Corpus-wide descriptive contrasts with both strong and weak post refs.

    These are not randomized comparisons and cannot prove a hook/placement
    was the cause of performance. Exclude missing percentiles and tiny groups.
    """
    result: list[dict[str, Any]] = []
    fields = [
        ("hook_technique", "hook mechanism", "LES-HOOK"),
        ("product_placement_style", "product placement", "LES-PLACEMENT"),
        ("dominant_visual_type", "visual treatment", "LES-VISUAL"),
        ("content_format", "content format", "LES-FORMAT-MIX"),
    ]
    for field, field_label, lesson_id in fields:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in posts:
            c = p.get("creative") or {}
            category = _text(c.get(field))
            if not category and field == "content_format":
                category = _text(c.get("video_format"))
            if category and _pct(p) is not None:
                grouped[category].append(p)
        eligible = [
            (category, group)
            for category, group in grouped.items() if len(group) >= 15
        ]
        if len(eligible) < 2:
            continue
        annotated = []
        for category, group in eligible:
            percentiles = [_pct(p) for p in group]
            usable = [float(value) for value in percentiles if value is not None]
            annotated.append({
                "category": category,
                "n": len(usable),
                "median_account_percentile": _median(usable),
                "source_high_low": sorted(
                    group, key=lambda p: _pct(p) or 0
                ),
            })
        annotated.sort(key=lambda x: (-x["n"],x["category"]))
        first_two = annotated[:2]
        examples: list[str] = []
        for group in first_two:
            for p in (group["source_high_low"][0], group["source_high_low"][-1]):
                if p["post_uid"] not in examples:
                    examples.append(p["post_uid"])
        short = "; ".join(
            f"{a['category']} ({a['n']} posts, median account percentile "
            f"{a['median_account_percentile']})"
            for a in first_two
        )
        result.append({
            "id": lesson_id,
            "kind": "observed_descriptive_contrast",
            "statement": (
                f"Two common {field_label} groups in the observed corpus: {short}."
            ),
            "source_post_uids": examples,
            "sample_count": sum(group["n"] for group in first_two),
            "action": (
                f"Pilot the {field_label} variants independently while "
                "holding the creative concept and account stable where possible."
            ),
            "qualification": (
                "Groups were not randomized or matched on topic, time or audience. "
                "Account-relative percentiles do not prove causal impact."
            ),
        })
    return result


def build_production_kit(
    *,
    evidence: dict[str, Any],
    families: dict[str, Any],
    accounts: dict[str, Any],
    lab: dict[str, Any] | None = None,
    recipes_limit: int = DEFAULT_RECIPES,
    calendar_days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    """Build a reproducible, public-evidence-linked production starter pack."""
    if not 1 <= recipes_limit <= MAX_RECIPES:
        raise ValueError(f"recipes_limit must be 1..{MAX_RECIPES}")
    if not 1 <= calendar_days <= MAX_DAYS:
        raise ValueError(f"calendar_days must be 1..{MAX_DAYS}")
    posts = evidence.get("posts") or []
    family_rows = families.get("families") or []
    account_rows = accounts.get("accounts") or []
    if not posts or not family_rows or not account_rows:
        raise ValueError("Production Kit needs posts, families and account baseline data.")
    post_map = {str(p["post_uid"]): p for p in posts if p.get("post_uid")}
    if len(post_map) != len(posts):
        raise ValueError("Duplicate or empty canonical post_uid in Production Kit source.")
    account_scopes = {str(a.get("operator_id")) for a in account_rows if a.get("operator_id")}
    post_scopes = {str(p.get("operator_id")) for p in posts if p.get("operator_id")}
    if len(account_scopes | post_scopes) != 1:
        raise ValueError("Production Kit must be scoped to exactly one operator.")
    operator_id = next(iter(account_scopes | post_scopes))
    source_digest = hashlib.sha256(json.dumps(
        {
            "posts": [
                (
                    p.get("post_uid"), p.get("views"), p.get("created_at"),
                    (p.get("creative") or {}).get("creative_formula"),
                    (p.get("creative") or {}).get("hook_text"),
                    [
                        (s.get("role"), s.get("primary_text"), s.get("visual_type"))
                        for s in p.get("sequence") or []
                    ],
                )
                for p in posts
            ],
            "family_members": [
                (
                    f.get("family_id"),
                    sorted(
                        str(m.get("post_uid"))
                        for m in f.get("members") or []
                    ),
                )
                for f in family_rows
            ],
        },
        sort_keys=True, ensure_ascii=False, default=str,
    ).encode("utf-8")).hexdigest()

    # A calendar should test each chosen recipe in comparable A/B slots,
    # not produce two singletons that cannot be compared.
    effective_limit = min(recipes_limit, max(1, calendar_days // 2))
    selected = _select_families(family_rows, post_map, effective_limit)
    if not selected:
        raise ValueError("No complete creative sequences available for production.")
    recipes: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    for idx, (fam, members, rank) in enumerate(selected, 1):
        recipe_id = f"REC-{idx:03d}"
        representative = max(
            members, key=lambda p: (_pct(p) or 0, _num(p.get("saves")) or 0)
        )
        c = representative.get("creative") or {}
        seq = sorted(representative.get("sequence") or [], key=lambda s: int(s.get("position") or 0))
        source_topic = _text(fam.get("core_topic") or c.get("topic"))
        source_hook = _text(fam.get("core_hook_text") or c.get("hook_text"))
        source_formula = _text(
            fam.get("core_hook_formula") or c.get("hook_replicable_formula")
            or c.get("creative_formula")
        )
        kind = _creative_kind(
            source_topic, _text(fam.get("core_angle") or c.get("content_angle")),
            source_hook,
        )
        subtype, proposed_title, proposed_steps = _editorial_spec(
            kind, topic=source_topic, hook=source_hook, formula=source_formula
        )
        pct_vals = [_pct(p) for p in members]
        pct_vals = [v for v in pct_vals if v is not None]
        source_posts = _reference_posts(members)
        if len(seq) < 2:
            seq = [
                {"role": "hook", "position": 1, "visual_type": c.get("dominant_visual_type")},
                {"role": "body", "position": 2, "visual_type": c.get("dominant_visual_type")},
                {"role": "body", "position": 3, "visual_type": c.get("dominant_visual_type")},
                {"role": "body", "position": 4, "visual_type": c.get("dominant_visual_type")},
                {"role": "product_reveal", "position": 5, "visual_type": "app_screen"},
            ]
        slides: list[dict[str, Any]] = []
        for sequence_idx, row in enumerate(seq[:10], 1):
            visual_type = _text(row.get("visual_type") or c.get("dominant_visual_type"))
            asset_id = f"AST-{idx:03d}-{sequence_idx:02d}"
            visual = _visual_query(visual_type, c.get("topic"))
            draft = _draft_for_role(
                kind, _text(row.get("role")), sequence_idx, len(seq[:10]),
                headline=proposed_title, body_steps=proposed_steps,
            )
            slides.append({
                "slide_number": sequence_idx,
                "role": _text(row.get("role") or "body"),
                "source_text_reference_only": _clean_copy(
                    row.get("primary_text") or row.get("overlay_text")
                ),
                "new_draft_text_vi": draft,
                "source_visual_description": _clean_copy(row.get("visual_description"), 320),
                "production_visual_brief": (
                    "Create/photograph an ORIGINAL asset inspired by the composition: "
                    + (_clean_copy(row.get("visual_description"), 170) or visual)
                    + ". Do not copy source media or branded screenshots."
                ),
                "visual_search_query": visual,
                "asset_id": asset_id,
                "visual_type": visual_type,
                "source_post_uid": representative["post_uid"],
            })
            assets.append({
                "asset_id": asset_id, "recipe_id": recipe_id,
                "kind": "image", "role": f"slide_{sequence_idx}",
                "search_query": visual,
                "reference_post_uid": representative["post_uid"],
                "reference_post_url": representative.get("url"),
                "file_or_licensed_source_url": "",
                "license_evidence_url": "",
                "license_scope": "",
                "rights_status": "not_verified",
                "production_status": "needs_original_or_licensed_asset",
                "safe_to_publish": False,
                "note": "TikTok/Pinterest appearance is a visual reference, not image reuse permission.",
            })
        sound_id = f"SOUND-{idx:03d}"
        assets.append({
            "asset_id": sound_id, "recipe_id": recipe_id,
            "kind": "music", "role": "background",
            "search_query": (
                "licensed calm instrumental study background audio"
                if kind not in {"motivation"} else "licensed gentle upbeat instrumental"
            ),
            "reference_post_uid": representative["post_uid"],
            "reference_post_url": representative.get("url"),
            "file_or_licensed_source_url": "",
            "license_evidence_url": "",
            "license_scope": "",
            "rights_status": "not_verified",
            "production_status": "sound_metadata_and_clearance_required",
            "safe_to_publish": False,
            "note": "Historical music ID not in Lab export; verify the sound and commercial-use rights.",
        })
        source_rights = "reference_only_not_licensed"
        grade = (
            "observed_multi_account_structure"
            if len({p.get("account_id") for p in members}) > 1
            else "observed_multi_execution_structure"
            if len(members) > 1
            else "single_observed_example"
        )
        recipes.append({
            "recipe_id": recipe_id, "family_id": fam.get("family_id"),
            "title": proposed_title,
            "creative_subtype": subtype,
            "concept_reference": _clean_copy(fam.get("core_topic") or c.get("topic")),
            "creative_angle": _text(c.get("content_angle") or fam.get("core_angle")),
            "hook_mechanism_reference": _clean_copy(
                fam.get("core_hook_formula") or c.get("hook_replicable_formula")
            ),
            "observed_original_hook_reference_only": _clean_copy(
                fam.get("core_hook_text") or c.get("hook_text")
            ),
            "new_hook_draft_vi": proposed_title,
            "content_type": representative.get("content_type"),
            "creative_kind": kind,
            "format": _text(c.get("content_format") or c.get("video_format")),
            "source_product_reference": c.get("product_family"),
            "slides": slides,
            "new_caption_draft_vi": (
                proposed_title + ". Lưu lại để thử rồi cho mình biết "
                "bạn đã điều chỉnh cách học nào nhé."
            ),
            "proposed_hashtags": ["#meohoc", "#studywithme", "#hoc_tap"],
            "proposed_cta": "Save this original checklist; share results, not guaranteed outcomes",
            "suggested_music_asset_id": sound_id,
            "observed_source_posts": source_posts,
            "evidence_grade": grade,
            "evidence": {
                "family_member_count": len(members),
                "distinct_accounts": len({p.get("account_id") for p in members}),
                "median_account_relative_views_percentile": _median(pct_vals),
                "lowest_account_relative_views_percentile": min(pct_vals) if pct_vals else None,
                "highest_account_relative_views_percentile": max(pct_vals) if pct_vals else None,
                "under_account_p35_examples": sum(v <= 0.35 for v in pct_vals),
                "selected_representative_uid": representative["post_uid"],
                "rank_for_editorial_inspection_only": rank,
                "chronology_not_causation": True,
            },
            "readiness": "draft_requires_copy_fact_check_and_asset_clearance",
            "rights_scope": source_rights,
            "is_proven_to_work_for_user": False,
            "editorial_checks": [
                "Review every generated slide against brand voice and factual sources.",
                "Use owned/licensed images and fonts; document rights.",
                "Confirm sound ID and TikTok/commercial usage terms in target region.",
                "No implication of proven operator intentions or expected views.",
                "Publish with authentic promotion disclosures when applicable.",
            ],
        })

    account_blueprints = _blueprints(account_rows, recipes, posts)
    calendar: list[dict[str, Any]] = []
    for day in range(1, calendar_days + 1):
        rec = recipes[(day - 1) % len(recipes)]
        # The two hook variants for a recipe must run on the SAME account.
        account = account_blueprints[
            ((day - 1) % len(recipes)) % len(account_blueprints)
        ]
        variant = "A" if ((day - 1) // len(recipes)) % 2 == 0 else "B"
        calendar.append({
            "day": day, "slot_id": f"PUB-{day:03d}",
            "pilot_account": account["slot_id"],
            "recipe_id": rec["recipe_id"],
            "family_id": rec["family_id"],
            "variant": variant,
            "test_dimension": "hook wording",
            "hook_to_publish_draft_vi": (
                rec["new_hook_draft_vi"] if variant == "A" else
                _VARIANT_SUBTYPE_HOOK_VI.get(
                    rec.get("creative_subtype"),
                    _VARIANT_HOOK_VI.get(rec["creative_kind"], _VARIANT_HOOK_VI["study_method"]),
                )
            ),
            "controlled_test": (
                "A/B test changes only the first-slide hook; keep account, "
                "visual style, CTA, content structure and slot constant "
                "unless separately tracked."
            ),
            "stop_or_recheck": (
                "Do not scale on a single post. Review at least five age-matched "
                "A/B pairs or stop earlier if copyright/fact review fails. "
                "Five pairs is a proposed experimental guardrail, NOT an "
                "operator-derived threshold."
            ),
            "planned_local_time": account["proposed_local_time"],
            "timezone": account["time_zone"],
            "time_basis": "proposed_experiment_not_validated_best_time",
            "content_type": rec["content_type"],
            "work_status": "draft",
            "publish_gate": "blocked_until_rights_and_copy_review",
            "measure_at": ["24h", "72h", "7d"],
            "tracking": "new_tracking_required",
            "primary_metric": "views_at_same_age_vs_own_recent_age_matched_baseline",
            "secondary_metrics": ["saves_per_view", "shares_per_view"],
            "post_url": "", "owner": "", "asset_clearance": "pending",
        })

    false_splits = _candidate_false_splits(family_rows, post_map)
    repeat_count = sum(int(f.get("member_count") or 0) > 1 for f in family_rows)
    cross_count = sum(bool(f.get("cross_account")) and int(f.get("member_count") or 0) > 1 for f in family_rows)
    sample_refs = [r["observed_source_posts"][0]["post_uid"] for r in recipes]
    observed_slides = sum(p.get("content_type") == "slideshow" for p in posts)
    lessons = [
        {
            "id": "LES-FORMAT", "kind": "observed",
            "statement": (
                f"{observed_slides} of {len(posts)} observed posts use a slideshow format."
            ),
            "source_post_uids": sample_refs[:8],
            "action": "Start with a small slideshow pilot; do not assume it beats videos.",
            "qualification": "Format prevalence does not establish causal performance.",
        },
        {
            "id": "LES-REUSE", "kind": "observed",
            "statement": (
                f"{repeat_count} candidate families contain multiple posts; "
                f"{cross_count} repeat across accounts."
            ),
            "source_family_ids": [r["family_id"] for r in recipes if r["evidence"]["family_member_count"] > 1],
            "action": "Test distinct original executions while tracking the same underlying concept.",
            "qualification": "Clustering may split or merge concepts incorrectly; no intent inferred.",
        },
        {
            "id": "LES-COUNTER", "kind": "bounded_inference",
            "statement": (
                "Repeated concepts show variable account-relative views; "
                "one execution does not determine another's result."
            ),
            "source_post_uids": sample_refs[:8],
            "action": "Collect underperforming as well as strong posts and compare account baselines.",
            "qualification": "No controlled test or future-success guarantee.",
        },
    ]
    lessons.extend(_tactical_observations(posts))
    return {
        "schema_version": SCHEMA_VERSION, "operator_id": operator_id,
        "source_post_count": len(posts),
        "source_family_count": len(family_rows),
        "source_account_count": len(account_rows),
        "source_fingerprint": source_digest,
        "research_context": {
            "source": "materialized Lab JSON (public posts + Vision interpretation)",
            "account_grouping": "researcher_declared_not_independent_ownership_proof",
            "calendar_timezone": "Asia/Ho_Chi_Minh",
            "planned_language": "vi",
            "assumptions": [
                "Two brand-owned pilot accounts are proposed, not observed operator roles.",
                "All new overlay/caption text is a DRAFT inspired by observed structure.",
                "Post source text is evidence-only; do not republish without permission.",
                "Historical posting hours are descriptive, not validated best posting times.",
                "No actual asset usage rights have been granted by this kit.",
            ],
        },
        "account_blueprints": account_blueprints,
        "recipes": recipes,
        "calendar": calendar,
        "asset_bank": assets,
        "music_bank": [],
        "caption_bank": [],
        "hashtag_bank": [],
        "suspected_false_splits": false_splits,
        "lessons": lessons,
        "quality": {
            "recipes_generated": len(recipes),
            "calendar_slots": len(calendar),
            "paired_ab_recipes": sum(
                {r["variant"] for r in calendar if r["recipe_id"] == recipe["recipe_id"]}
                >= {"A", "B"}
                for recipe in recipes
            ),
            "post_evidence_links": sum(len(r["observed_source_posts"]) for r in recipes),
            "slides_drafted": sum(len(r["slides"]) for r in recipes),
            "asset_candidates": len(assets),
            "false_split_candidates": len(false_splits),
            "false_split_diagnostics_capped_at": 50,
            "corpus_observations": len(lessons),
            "assets_with_verified_rights": 0,
            "ready_to_publish": 0,
            "sound_metadata_coverage": 0,
            "raw_enrichment": "not_supplied",
            "source_coverage_is_sample_not_full_license_audit": True,
            "readiness": "TEAM_BRIEF_DRAFT_not_auto_publishable",
        },
    }



def apply_team_asset_clearance(
    kit: dict[str, Any], rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Record team attestations, not automatic legal/third-party verification."""
    assets_by_id = {row["asset_id"]: row for row in kit["asset_bank"]}
    seen: set[str] = set()
    for row in rows:
        aid = _text(row.get("asset_id"))
        if aid not in assets_by_id or aid in seen:
            raise ValueError(f"Unknown/duplicate asset ID in clearance CSV: {aid}")
        seen.add(aid)
        asset = assets_by_id[aid]
        status = _text(row.get("rights_status"))
        if status not in {"not_verified", "team_attested_licensed"}:
            raise ValueError(f"Invalid asset rights_status for {aid}")
        if status == "team_attested_licensed":
            location = _text(row.get("file_or_licensed_source_url"))
            evidence_url = _text(row.get("license_evidence_url"))
            verifier = _text(row.get("verified_by"))
            scope = _text(row.get("license_scope"))
            if not all((location, evidence_url, verifier, scope)):
                raise ValueError(f"Asset {aid} lacks evidence, ownership, or license scope")
            if "tiktok" not in scope.casefold():
                raise ValueError(f"Asset {aid} not licensed for target platform TikTok")
            asset.update({
                "file_or_licensed_source_url": location,
                "license_evidence_url": evidence_url,
                "license_scope": scope,
                "rights_status": status,
                "production_status": "team_attested_rights_editorial_review_pending",
                # Attestation of rights is not proof that copy, claims, partner
                # disclosures, brand policy and TikTok terms have been checked.
                "safe_to_publish": False,
                "verified_by": verifier,
                "rights_verified_at": _text(row.get("verified_at")),
            })
    kit["quality"]["assets_with_verified_rights"] = sum(
        asset["rights_status"] == "team_attested_licensed"
        for asset in kit["asset_bank"]
    )
    kit["quality"]["ready_to_publish"] = 0
    return kit


def attach_own_experiment_outcomes(
    kit: dict[str, Any], rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Track actual first-party results with provenance, including failures."""
    valid_recipes = {r["recipe_id"] for r in kit["recipes"]}
    outcome_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        recipe_id = _text(row.get("recipe_id"))
        if recipe_id not in valid_recipes:
            raise ValueError(f"Outcome row {index}: unknown recipe_id {recipe_id!r}")
        views = _num(row.get("views"))
        baseline = _num(row.get("account_median_views"))
        saves = _num(row.get("saves"))
        shares = _num(row.get("shares"))
        if views is not None and views < 0:
            raise ValueError(f"Outcome row {index}: negative views")
        if baseline is not None and baseline <= 0:
            raise ValueError(f"Outcome row {index}: baseline must be > 0")
        if any(v is not None and v < 0 for v in (saves, shares)):
            raise ValueError(f"Outcome row {index}: negative interaction count")
        comparison = round(views / baseline, 3) if views is not None and baseline else None
        outcome_rows.append({
            "recipe_id": recipe_id,
            "account_slot": _text(row.get("account_slot")),
            "published_url": _text(row.get("published_url")),
            "posted_at": _text(row.get("posted_at")),
            "measurement_age_hours": _num(row.get("measurement_age_hours")),
            "views": views, "saves": saves, "shares": shares,
            "account_median_views": baseline,
            "views_vs_account_median": comparison,
            "saves_per_view": round(saves / views, 6) if views and saves is not None else None,
            "shares_per_view": round(shares / views, 6) if views and shares is not None else None,
            "editorial_notes": _clean_copy(row.get("notes"), 800),
            "evidence_origin": "first_party_team_reported_not_scraped_operator",
            "causal_claim": False,
        })
    kit["own_experiment_outcomes"] = outcome_rows
    kit["quality"]["first_party_results_recorded"] = len(outcome_rows)
    return kit


