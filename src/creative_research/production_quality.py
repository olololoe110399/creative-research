"""Integrity of source citations, rights boundaries and production handoff."""
from __future__ import annotations
from typing import Any
from creative_research.production_contracts import SCHEMA_VERSION

def audit_production_kit(
    kit: dict[str, Any],
    post_ids: set[str] | None = None,
    family_ids: set[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if kit.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_production_kit_schema")
    recipe_rows = kit.get("recipes") or []
    recipe_ids = [r.get("recipe_id") for r in recipe_rows]
    if not recipe_ids or len(recipe_ids) != len(set(recipe_ids)):
        errors.append("empty_or_duplicate_recipe_ids")
    asset_rows = kit.get("asset_bank") or []
    asset_ids = [a.get("asset_id") for a in asset_rows]
    if len(asset_ids) != len(set(asset_ids)):
        errors.append("duplicate_asset_ids")
    for recipe in recipe_rows:
        rid = recipe.get("recipe_id")
        if family_ids is not None and recipe.get("family_id") not in family_ids:
            errors.append(f"{rid}:orphan_source_family")
        if not recipe.get("observed_source_posts"):
            errors.append(f"{rid}:missing_source_posts")
        if not recipe.get("slides"):
            errors.append(f"{rid}:no_production_slides")
        if recipe.get("is_proven_to_work_for_user") is not False:
            errors.append(f"{rid}:unjustified_success_claim")
        if recipe.get("readiness") != "draft_requires_copy_fact_check_and_asset_clearance":
            errors.append(f"{rid}:missing_readiness_warning")
        for post in recipe.get("observed_source_posts", []):
            if not post.get("post_uid") or not post.get("url"):
                errors.append(f"{rid}:untraceable_post")
            if post_ids is not None and post.get("post_uid") not in post_ids:
                errors.append(f"{rid}:orphan_post_reference")
        for slide in recipe.get("slides", []):
            if slide.get("asset_id") not in asset_ids:
                errors.append(f"{rid}:slide_without_asset")
    for asset in asset_rows:
        if asset.get("recipe_id") not in recipe_ids:
            errors.append(f"{asset.get('asset_id')}:orphan_asset_recipe")
        if asset.get("rights_status") != "team_attested_licensed" and asset.get("safe_to_publish"):
            errors.append(f"{asset.get('asset_id')}:unlicensed_asset_marked_publishable")
    for sound in kit.get("music_bank", []):
        if sound.get("usable_as_commercial_sound") is not False:
            errors.append(f"{sound.get('sound_key')}:sound_rights_not_verified")
    for match in kit.get("suspected_false_splits", []):
        if match.get("validated_same_concept") is not False:
            errors.append("unverified_family_split_presented_as_fact")
    for calendar in kit.get("calendar", []):
        if calendar.get("recipe_id") not in recipe_ids:
            errors.append(f"{calendar.get('slot_id')}:orphan_calendar_recipe")
        if calendar.get("publish_gate") != "blocked_until_rights_and_copy_review":
            errors.append(f"{calendar.get('slot_id')}:unsafe_publish_gate")
        if calendar.get("tracking") != "new_tracking_required":
            errors.append(f"{calendar.get('slot_id')}:unsupported_existing_tracking_claim")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "schema_version": SCHEMA_VERSION,
        "recipes_checked": len(recipe_rows),
        "calendar_slots_checked": len(kit.get("calendar", [])),
        "asset_candidates_checked": len(asset_rows),
        "meaning": (
            "Lineage, honesty and handoff contract check; not external "
            "copyright verification, creative accuracy, or proven outcomes."
        ),
    }


