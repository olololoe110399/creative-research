"""Team-facing ZIP/CSV/Markdown export; never grants source-media usage rights."""
from __future__ import annotations
import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any
from creative_research.production_quality import audit_production_kit

def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            column: (
                json.dumps(row.get(column), ensure_ascii=False)
                if isinstance(row.get(column), (dict, list))
                else row.get(column)
            )
            for column in columns
        })
    return stream.getvalue().encode("utf-8-sig")


def _source_markdown(recipe: dict[str, Any]) -> str:
    source_links = "\n".join(
        f"- {p['post_uid']} / @{p.get('account')}: {p.get('url')} "
        f"(views {p.get('views')}, own-account percentile "
        f"{p.get('account_relative_views_percentile')})"
        for p in recipe["observed_source_posts"]
    )
    slides = "\n".join(
        f"### Slide/scene {s['slide_number']} — {s['role']}\n\n"
        f"New Vietnamese draft: {s['new_draft_text_vi']}\n\n"
        f"Make original visual: {s['production_visual_brief']}\n\n"
        f"Reference-only text: {s['source_text_reference_only']}\n\n"
        f"Search prompt: {s['visual_search_query']} | asset {s['asset_id']}\n"
        for s in recipe["slides"]
    )
    return (
        f"# {recipe['recipe_id']} — {recipe['title']}\n\n"
        "STATUS: Draft for editorial fact-check and LICENSED/ORIGINAL ASSETS. "
        "Not approved for publication as-is.\n\n"
        f"Evidence grade: {recipe['evidence_grade']}\n\n"
        f"Creative structure: {recipe['hook_mechanism_reference']}\n\n"
        f"New hook: {recipe['new_hook_draft_vi']}\n\n"
        f"Original operator hook (EVIDENCE ONLY): "
        f"{recipe['observed_original_hook_reference_only']}\n\n"
        f"Observed evidence: {json.dumps(recipe['evidence'],ensure_ascii=False,indent=2)}\n\n"
        "## Research source links\n\n"+source_links+"\n\n"
        "## Production storyboard\n\n"+slides+"\n\n"
        f"## Caption draft\n\n{recipe['new_caption_draft_vi']}\n\n"
        f"Proposed hashtags: {' '.join(recipe['proposed_hashtags'])}\n\n"
        f"Sound to source: {recipe['suggested_music_asset_id']}; rights NOT verified.\n\n"
        "## Do not publish before\n\n"+
        "\n".join(f"- [ ] {check}" for check in recipe["editorial_checks"])+"\n"
    )


def _summary_md(kit: dict[str, Any]) -> str:
    q = kit["quality"]
    return (
        "# Production Handoff — START HERE\n\n"
        f"Operator reference: {kit['operator_id']} "
        "(public posts, researcher-declared account grouping)\n\n"
        f"Source: {kit['source_post_count']} posts; "
        f"{kit['source_family_count']} family candidates; "
        f"{kit['source_account_count']} accounts.\n\n"
        f"Prepared: {q['recipes_generated']} recipes, {q['slides_drafted']} "
        f"slides/scenes, {q['calendar_slots']} planned posts and "
        f"{q['asset_candidates']} required asset candidates.\n\n"
        "## Team handoff order\n\n"
        "1. Read ACCOUNT_BLUEPRINTS.md and own the pilot account identities.\n"
        "2. Open CONTENT_PLAN.csv. Each slot points to one numbered recipe.\n"
        "3. Open briefs/REC-xxx.md for new overlay copy, per-slide visual "
        "directions, caption draft and source TikTok links.\n"
        "4. Work through ASSET_BANK.csv: photograph/create original images, "
        "document file and permission source, then verify TikTok-appropriate "
        "music rights. Pinterest references are NOT licensed assets.\n"
        "5. Record brand factual/claims review and any promotion disclosures. "
        "Only then mark a calendar slot ready in your own production tracker.\n"
        "6. Record your own post URLs, 24h/72h/7d metrics in "
        "OWN_RESULTS_TEMPLATE.csv. Re-export to get evidence-labelled learnings.\n\n"
        "## NON-NEGOTIABLE EVIDENCE LIMITS\n\n"
        "- The operator's internal test/scale workflow has NOT been proven.\n"
        "- The source hooks/media are references only; draft text must be "
        "fact-checked and edited in the team's own voice.\n"
        "- No asset here is automatically licensed, and no content is "
        "automatically marked ready to publish.\n"
        "- Publishing times/2-account pilot structure are proposed "
        "experiments, NOT statistically validated operator advice.\n"
        "- Individual historical high views do not predict your own outcomes.\n\n"
        f"Raw caption/music enrichment: {q['raw_enrichment']}. "
        f"Music references found: {len(kit['music_bank'])}; "
        f"team-attested assets: {q['assets_with_verified_rights']}.\n"
    )


def production_kit_artifacts(kit: dict[str, Any]) -> dict[str, bytes]:
    """All team files; stable path names, no external media or credentials."""
    audit = audit_production_kit(kit)
    if audit["status"] != "pass":
        raise ValueError("Invalid production kit: "+", ".join(audit["errors"][:12]))
    accounts_md = "# Original-account launch blueprint (proposals, not observed intent)\n\n"
    for a in kit["account_blueprints"]:
        accounts_md += (
            f"## {a['slot_id']}: {a['positioning']}\n\n"
            f"Audience: {a['audience']}\n\n"
            f"Handle pattern: {a['suggested_handle_pattern']}\n\n"
            f"Bio draft: {a['bio_draft']}\n\n"
            f"Avatar: {a['avatar_brief']}\n\n"
            f"Pilot cadence: {a['proposed_cadence']} at "
            f"{a['proposed_local_time']} {a['time_zone']} "
            "(UNVALIDATED EXPERIMENT TIME)\n\n"
            "Setup checklist:\n"+
            "\n".join(f"- [ ] {s}" for s in a["setup_checklist"])+
            "\n\nObserved reference accounts: "+
            ", ".join(str(s["handle"]) for s in a["source_account_observations"])+
            "\n\n"
        )
    result: dict[str, bytes] = {
        "START_HERE.md": _summary_md(kit).encode("utf-8"),
        "ACCOUNT_BLUEPRINTS.md": accounts_md.encode("utf-8"),
        "PRODUCTION.json": json.dumps(kit,ensure_ascii=False,indent=2,default=str).encode("utf-8"),
        "CONTENT_PLAN.csv": _csv_bytes(kit["calendar"], [
            "day", "slot_id", "pilot_account", "recipe_id", "family_id",
            "variant", "test_dimension", "hook_to_publish_draft_vi",
            "controlled_test", "stop_or_recheck",
            "planned_local_time", "timezone",
            "time_basis", "content_type", "work_status", "publish_gate",
            "tracking", "primary_metric", "secondary_metrics",
            "post_url", "owner", "asset_clearance",
        ]),
        "ASSET_BANK.csv": _csv_bytes(kit["asset_bank"], [
            "asset_id", "recipe_id", "kind", "role", "search_query",
            "reference_post_uid", "reference_post_url",
            "observed_sound_key", "file_or_licensed_source_url",
            "license_evidence_url", "license_scope", "rights_status",
            "production_status", "safe_to_publish", "verified_by", "note",
        ]),
        "SOUND_BANK.csv": _csv_bytes(kit["music_bank"], [
            "sound_key", "music_id", "music_name", "music_author",
            "observed_post_count", "source_post_uids", "source_urls",
            "license_status", "rights_scope", "usable_as_commercial_sound", "source",
        ]),
        "CAPTION_BANK.csv": _csv_bytes(kit.get("caption_bank", []), [
            "post_uid", "account", "url", "caption_reference_only",
            "views_percentile_account", "rights_scope",
        ]),
        "HASHTAG_BANK.csv": _csv_bytes(kit.get("hashtag_bank", []), [
            "hashtag", "observed_post_count", "example_post_uids",
            "usage_not_recommended_without_relevance_check",
        ]),
        "SOURCE_EVIDENCE.csv": _csv_bytes([
            {"recipe_id": r["recipe_id"], "family_id": r["family_id"],
             **p, "evidence_grade": r["evidence_grade"]}
            for r in kit["recipes"] for p in r["observed_source_posts"]
        ], [
            "recipe_id", "family_id", "post_uid", "account", "post_id", "url",
            "views", "account_relative_views_percentile", "saves",
            "created_at", "hook_reference", "evidence_grade",
            "observed_caption_reference_only", "observed_hashtags_reference_only",
        ]),
        "SUSPECTED_FALSE_SPLITS.csv": _csv_bytes(kit["suspected_false_splits"], [
            "family_a", "family_b", "post_a", "post_b", "url_a", "url_b",
            "accounts", "shared_hook_reference", "matching_sequence_roles",
            "shared_product_family", "finding", "validated_same_concept",
        ]),
        "ASSET_CLEARANCE_TEMPLATE.csv": _csv_bytes([], [
            "asset_id", "rights_status", "file_or_licensed_source_url",
            "license_evidence_url", "license_scope", "verified_by", "verified_at",
        ]),
        "OWN_RESULTS_TEMPLATE.csv": _csv_bytes([], [
            "recipe_id", "account_slot", "published_url", "posted_at",
            "measurement_age_hours", "views", "saves", "shares",
            "account_median_views", "notes",
        ]),
        "OWN_EXPERIMENT_RESULTS.csv": _csv_bytes(
            kit.get("own_experiment_outcomes", []), [
                "recipe_id", "account_slot", "published_url", "posted_at",
                "measurement_age_hours", "views", "saves", "shares",
                "account_median_views", "views_vs_account_median",
                "saves_per_view", "shares_per_view",
                "editorial_notes", "evidence_origin",
            ],
        ),
        "QUALITY_REPORT.json": json.dumps(audit, ensure_ascii=False, indent=2).encode("utf-8"),
        "LESSONS.md": (
            "# Evidence-bound lessons, not operator intent\n\n"+
            "\n\n".join(
                f"## {l['id']} ({l['kind']})\n\n"
                f"Observation: {l['statement']}\n\n"
                f"Trial: {l['action']}\n\n"
                f"Limit: {l['qualification']}\n\n"
                for l in kit["lessons"]
            )
        ).encode("utf-8"),
    }
    for recipe in kit["recipes"]:
        result[f"briefs/{recipe['recipe_id']}.md"] = _source_markdown(recipe).encode("utf-8")
    return result


def write_production_kit(
    kit: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    audit = audit_production_kit(kit)
    if audit["status"] != "pass":
        raise ValueError("Production Kit fails evidence quality gate: "+str(audit["errors"][:10]))
    artifacts = production_kit_artifacts(kit)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as package:
        for name, content in sorted(artifacts.items()):
            package.writestr(name, content)
    production = workspace / "production.json"
    handoff = workspace / "production-kit.zip"
    # Avoid partially writing the public entry-point JSON if package build fails.
    handoff.write_bytes(archive.getvalue())
    production.write_text(
        json.dumps(kit, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return {
        "workspace": str(workspace),
        "production_json": str(production),
        "handoff_zip": str(handoff),
        "handoff_bytes": len(archive.getvalue()),
        "entries": len(artifacts),
        "quality": audit,
    }
