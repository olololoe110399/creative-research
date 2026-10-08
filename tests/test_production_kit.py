from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from creative_research.production_kit import (
    apply_team_asset_clearance,
    attach_own_experiment_outcomes,
    audit_production_kit,
    build_production_kit,
    enrich_production_kit_from_raw,
    write_production_kit,
)


def _fixture() -> tuple[dict, dict, dict]:
    def post(uid: str, account: str, pid: str, pct: float, views: int):
        return {
            "post_uid": uid,
            "operator_id": "OP1",
            "account_id": account,
            "account": account.lower(),
            "post_id": pid,
            "url": f"https://www.tiktok.com/@{account.lower()}/video/{pid}",
            "created_at": "2025-03-01T12:00:00+00:00",
            "content_type": "slideshow",
            "views": views, "saves": int(views * .04),
            "save_rate": .04,
            "performance": {"views_percentile_account": pct},
            "creative": {
                "primary_language_code": "en",
                "topic": "study schedules for different types of students",
                "content_angle": "study_method",
                "hook_text": "Study schedules for different students",
                "hook_replicable_formula": "Categorize student personas and adapt study schedules",
                "product_family": "study_app",
                "content_format": "listicle",
                "dominant_visual_type": "study_desk_photo",
            },
            "sequence": [
                {"position": 1, "role": "hook",
                 "primary_text": "Study schedules for different students",
                 "visual_type": "study_desk_photo",
                 "visual_description": "Original overhead study desk photo"},
                {"position": 2, "role": "body",
                 "primary_text": "Morning student study plan",
                 "visual_type": "study_desk_photo",
                 "visual_description": "Table of early morning study time"},
                {"position": 3, "role": "product_reveal",
                 "primary_text": "Feynman",
                 "visual_type": "app_screen",
                 "visual_description": "A study app screen"},
            ],
        }
    posts = [
        post("P1", "Alpha", "111", .82, 10000),
        post("P2", "Beta", "222", .13, 100),
        post("P3", "Alpha", "333", .91, 18000),
    ]
    posts[2]["creative"]["topic"] = "how to revise for exams"
    posts[2]["creative"]["hook_text"] = "Exam revision framework"
    posts[2]["creative"]["hook_replicable_formula"] = "Turn exam mistakes into review tasks"
    families = [
        {
            "family_id": "F1", "member_count": 2, "accounts_count": 2,
            "cross_account": True, "core_topic": posts[0]["creative"]["topic"],
            "core_hook_formula": posts[0]["creative"]["hook_replicable_formula"],
            "core_hook_text": posts[0]["creative"]["hook_text"],
            "members": [{"post_uid": "P1"}, {"post_uid": "P2"}],
        },
        {
            "family_id": "F2", "member_count": 1,
            "family_origin_post_uid": "P3", "representative_post_uid": "P3",
            "core_topic": posts[2]["creative"]["topic"],
            "core_hook_formula": posts[2]["creative"]["hook_replicable_formula"],
            "members": [{"post_uid": "P3"}],
        },
    ]
    accounts = [
        {"operator_id": "OP1", "account_id": "Alpha",
         "account": "alpha", "observed_posts": 2,
         "performance_baseline": {"median_views": 14000},
         "cadence_summary": {"median_gap_hours": 24.0,
                             "top_posting_hours_json": '[{"value": 15, "posts": 2}]'}},
        {"operator_id": "OP1", "account_id": "Beta",
         "account": "beta", "observed_posts": 1,
         "performance_baseline": {"median_views": 100},
         "cadence_summary": {"median_gap_hours": None}},
    ]
    return {"posts": posts}, {"families": families}, {"accounts": accounts}


def test_creator_kit_builds_source_linked_storyboards_calendar_and_blocked_assets(
    tmp_path: Path,
) -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence, families=families, accounts=accounts,
        recipes_limit=2, calendar_days=14,
    )
    assert kit["schema_version"] == "creator-production-kit-v1"
    assert kit["operator_id"] == "OP1"
    assert kit["source_post_count"] == 3
    assert len(kit["recipes"]) == 2
    assert len(kit["calendar"]) == 14
    assert all(s["tracking"] == "new_tracking_required" for s in kit["calendar"])
    assert {r["evidence_grade"] for r in kit["recipes"]} == {
        "observed_multi_account_structure", "single_observed_example"
    }
    repeated = next(r for r in kit["recipes"] if r["family_id"] == "F1")
    assert repeated["evidence"]["under_account_p35_examples"] == 1
    assert {p["post_uid"] for p in repeated["observed_source_posts"]} == {"P1", "P2"}
    assert repeated["observed_original_hook_reference_only"]
    assert repeated["new_hook_draft_vi"] != repeated["observed_original_hook_reference_only"]
    assert all(s["new_draft_text_vi"] for s in repeated["slides"])
    assert all(s["visual_search_query"] for s in repeated["slides"])
    assert all(a["rights_status"] == "not_verified" for a in kit["asset_bank"])
    assert kit["quality"]["ready_to_publish"] == 0
    assert audit_production_kit(kit, {p["post_uid"] for p in evidence["posts"]})["status"] == "pass"

    output = write_production_kit(kit, workspace=tmp_path)
    assert output["quality"]["status"] == "pass"
    with zipfile.ZipFile(tmp_path/"production-kit.zip") as z:
        assert z.testzip() is None
        names = set(z.namelist())
        assert "START_HERE.md" in names
        assert "ACCOUNT_BLUEPRINTS.md" in names
        assert "CONTENT_PLAN.csv" in names
        assert "ASSET_BANK.csv" in names
        assert "SOUND_BANK.csv" in names
        assert "SOURCE_EVIDENCE.csv" in names
        assert "SUSPECTED_FALSE_SPLITS.csv" in names
        assert "OWN_RESULTS_TEMPLATE.csv" in names
        assert "br‌iefs/REC-001.md" not in names
        assert "briefs/REC-001.md" in names
        assert "briefs/REC-002.md" in names
        assert "EVIDENCE ONLY" in z.read("briefs/REC-001.md").decode()


def test_raw_music_enrichment_retains_provenance_but_never_grants_rights(tmp_path: Path) -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence, families=families, accounts=accounts,
        recipes_limit=2, calendar_days=4,
    )
    raw = tmp_path/"scraped"/"raw"
    raw.mkdir(parents=True)
    (raw/"all_items.jsonl").write_text(json.dumps({
        "id": "111",
        "input": "alpha",
        "text": "Observed original caption",
        "hashtags": [{"name": "studytok"}],
        "musicMeta": {
            "musicId": "SOUND777", "musicName": "Unknown study track",
            "musicAuthor": "Reference artist",
        },
    }) + "\n", encoding="utf-8")
    enriched = enrich_production_kit_from_raw(kit, tmp_path/"scraped")
    assert enriched["quality"]["raw_posts_matched"] == 1
    assert enriched["quality"]["observed_sound_post_count"] == 1
    assert enriched["music_bank"][0]["music_id"] == "SOUND777"
    assert enriched["music_bank"][0]["license_status"] == "not_verified"
    assert enriched["music_bank"][0]["usable_as_commercial_sound"] is False
    assert enriched["quality"]["ready_to_publish"] == 0


def test_rights_attestation_requires_proof_and_never_autopublishes() -> None:
    kit = build_production_kit(
        evidence=_fixture()[0], families=_fixture()[1], accounts=_fixture()[2],
    )
    aid = kit["asset_bank"][0]["asset_id"]
    with pytest.raises(ValueError, match="lacks evidence"):
        apply_team_asset_clearance(kit, [{
            "asset_id": aid, "rights_status": "team_attested_licensed",
        }])
    with pytest.raises(ValueError, match="target platform"):
        apply_team_asset_clearance(kit, [{
            "asset_id": aid, "rights_status": "team_attested_licensed",
            "file_or_licensed_source_url": "owned/desk.jpg",
            "license_evidence_url": "team-policy-note",
            "license_scope": "website",
            "verified_by": "editor",
        }])
    changed = apply_team_asset_clearance(kit, [{
        "asset_id": aid, "rights_status": "team_attested_licensed",
        "file_or_licensed_source_url": "owned/desk.jpg",
        "license_evidence_url": "team-policy-note",
        "license_scope": "TikTok organic and commercial",
        "verified_by": "editor",
    }])
    assert changed["quality"]["assets_with_verified_rights"] == 1
    assert changed["quality"]["ready_to_publish"] == 0
    assert next(a for a in changed["asset_bank"] if a["asset_id"] == aid)["safe_to_publish"] is False
    assert audit_production_kit(changed)["status"] == "pass"


def test_first_party_results_are_not_claimed_as_operator_success() -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence, families=families, accounts=accounts,
        recipes_limit=2,
    )
    changed = attach_own_experiment_outcomes(kit, [
        {
            "recipe_id": kit["recipes"][0]["recipe_id"],
            "account_slot": "PILOT-A",
            "published_url": "https://www.tiktok.com/@myaccount/video/123",
            "views": "1000", "account_median_views": "400",
            "saves": "14", "shares": "4",
            "notes": "Original creative, one test only",
        },
    ])
    record = changed["own_experiment_outcomes"][0]
    assert record["views_vs_account_median"] == 2.5
    assert record["evidence_origin"] == "first_party_team_reported_not_scraped_operator"
    assert record["causal_claim"] is False
    with pytest.raises(ValueError, match="unknown recipe_id"):
        attach_own_experiment_outcomes(kit, [{"recipe_id": "BAD"}])


def test_suspected_false_split_is_a_candidate_not_a_silent_merge() -> None:
    evidence, families, accounts = _fixture()
    original = dict(evidence["posts"][0])
    cloned = {
        **original, "post_uid": "P4", "account_id": "Beta",
        "account": "beta", "post_id": "444",
        "url": "https://www.tiktok.com/@beta/video/444",
    }
    evidence["posts"].append(cloned)
    families["families"].append({
        "family_id": "F3", "member_count": 1,
        "family_origin_post_uid": "P4", "core_hook_text": "Study schedules for different students",
        "members": [{"post_uid": "P4"}],
    })
    families["families"].append({
        "family_id": "F4", "member_count": 1,
        "family_origin_post_uid": "P1", "core_hook_text": "Study schedules for different students",
        "members": [{"post_uid": "P1"}],
    })
    kit = build_production_kit(
        evidence=evidence, families=families, accounts=accounts,
        recipes_limit=3,
    )
    candidates = kit["suspected_false_splits"]
    assert any(
        {c["family_a"], c["family_b"]} == {"F3", "F4"}
        for c in candidates
    )
    assert all(c["validated_same_concept"] is False for c in candidates)


def test_orphan_reference_and_false_rights_fail_quality_gate() -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence, families=families, accounts=accounts,
    )
    kit["recipes"][0]["observed_source_posts"][0]["post_uid"] = "ORPHAN"
    assert "orphan_post_reference" in "|".join(
        audit_production_kit(kit, {"P1", "P2", "P3"})["errors"]
    )
    kit = build_production_kit(
        evidence=evidence, families=families, accounts=accounts,
    )
    kit["asset_bank"][0]["safe_to_publish"] = True
    assert "unlicensed_asset_marked_publishable" in "|".join(
        audit_production_kit(kit)["errors"]
    )
