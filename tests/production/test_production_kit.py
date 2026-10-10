from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from creative_research.production.handoff import write_production_kit
from creative_research.production.kit import (
    _editorial_spec,
    apply_team_asset_clearance,
    attach_own_experiment_outcomes,
    build_production_kit,
)
from creative_research.production.quality import audit_production_kit
from creative_research.production.sources import enrich_production_kit_from_raw


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
            "views": views,
            "saves": int(views * 0.04),
            "save_rate": 0.04,
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
                {
                    "position": 1,
                    "role": "hook",
                    "primary_text": "Study schedules for different students",
                    "visual_type": "study_desk_photo",
                    "visual_description": "Original overhead study desk photo",
                },
                {
                    "position": 2,
                    "role": "body",
                    "primary_text": "Morning student study plan",
                    "visual_type": "study_desk_photo",
                    "visual_description": "Table of early morning study time",
                },
                {
                    "position": 3,
                    "role": "product_reveal",
                    "primary_text": "Feynman",
                    "visual_type": "app_screen",
                    "visual_description": "A study app screen",
                },
            ],
        }

    posts = [
        post("P1", "Alpha", "111", 0.82, 10000),
        post("P2", "Beta", "222", 0.13, 100),
        post("P3", "Alpha", "333", 0.91, 18000),
    ]
    posts[2]["creative"]["topic"] = "how to revise for exams"
    posts[2]["creative"]["hook_text"] = "Exam revision framework"
    posts[2]["creative"]["hook_replicable_formula"] = "Turn exam mistakes into review tasks"
    families = [
        {
            "family_id": "F1",
            "member_count": 2,
            "accounts_count": 2,
            "cross_account": True,
            "core_topic": posts[0]["creative"]["topic"],
            "core_hook_formula": posts[0]["creative"]["hook_replicable_formula"],
            "core_hook_text": posts[0]["creative"]["hook_text"],
            "members": [{"post_uid": "P1"}, {"post_uid": "P2"}],
        },
        {
            "family_id": "F2",
            "member_count": 1,
            "family_origin_post_uid": "P3",
            "representative_post_uid": "P3",
            "core_topic": posts[2]["creative"]["topic"],
            "core_hook_formula": posts[2]["creative"]["hook_replicable_formula"],
            "members": [{"post_uid": "P3"}],
        },
    ]
    accounts = [
        {
            "operator_id": "OP1",
            "account_id": "Alpha",
            "account": "alpha",
            "observed_posts": 2,
            "performance_baseline": {"median_views": 14000},
            "cadence_summary": {
                "median_gap_hours": 24.0,
                "top_posting_hours_json": '[{"value": 15, "posts": 2}]',
            },
        },
        {
            "operator_id": "OP1",
            "account_id": "Beta",
            "account": "beta",
            "observed_posts": 1,
            "performance_baseline": {"median_views": 100},
            "cadence_summary": {"median_gap_hours": None},
        },
    ]
    return {"posts": posts}, {"families": families}, {"accounts": accounts}


def test_creator_kit_builds_source_linked_storyboards_calendar_and_blocked_assets(
    tmp_path: Path,
) -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
        recipes_limit=2,
        calendar_days=14,
    )
    assert kit["schema_version"] == "creator-production-kit-v1"
    assert kit["operator_id"] == "OP1"
    assert kit["source_post_count"] == 3
    assert len(kit["recipes"]) == 2
    assert len(kit["calendar"]) == 14
    assert all(s["tracking"] == "new_tracking_required" for s in kit["calendar"])
    assert {r["evidence_grade"] for r in kit["recipes"]} == {
        "observed_multi_account_structure",
        "single_observed_example",
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
    with zipfile.ZipFile(tmp_path / "production-kit.zip") as z:
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
        evidence=evidence,
        families=families,
        accounts=accounts,
        recipes_limit=2,
        calendar_days=4,
    )
    raw = tmp_path / "scraped" / "raw"
    raw.mkdir(parents=True)
    (raw / "all_items.jsonl").write_text(
        json.dumps(
            {
                "id": "111",
                "input": "alpha",
                "text": "Observed original caption",
                "hashtags": [{"name": "studytok"}],
                "musicMeta": {
                    "musicId": "SOUND777",
                    "musicName": "Unknown study track",
                    "musicAuthor": "Reference artist",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    enriched = enrich_production_kit_from_raw(kit, tmp_path / "scraped")
    assert enriched["quality"]["raw_posts_matched"] == 1
    assert enriched["quality"]["observed_sound_post_count"] == 1
    assert enriched["music_bank"][0]["music_id"] == "SOUND777"
    assert enriched["music_bank"][0]["license_status"] == "not_verified"
    assert enriched["music_bank"][0]["usable_as_commercial_sound"] is False
    assert enriched["quality"]["ready_to_publish"] == 0


def test_rights_attestation_requires_proof_and_never_autopublishes() -> None:
    kit = build_production_kit(
        evidence=_fixture()[0],
        families=_fixture()[1],
        accounts=_fixture()[2],
    )
    aid = kit["asset_bank"][0]["asset_id"]
    with pytest.raises(ValueError, match="lacks evidence"):
        apply_team_asset_clearance(
            kit,
            [
                {
                    "asset_id": aid,
                    "rights_status": "team_attested_licensed",
                }
            ],
        )
    with pytest.raises(ValueError, match="target platform"):
        apply_team_asset_clearance(
            kit,
            [
                {
                    "asset_id": aid,
                    "rights_status": "team_attested_licensed",
                    "file_or_licensed_source_url": "owned/desk.jpg",
                    "license_evidence_url": "team-policy-note",
                    "license_scope": "website",
                    "verified_by": "editor",
                }
            ],
        )
    changed = apply_team_asset_clearance(
        kit,
        [
            {
                "asset_id": aid,
                "rights_status": "team_attested_licensed",
                "file_or_licensed_source_url": "owned/desk.jpg",
                "license_evidence_url": "team-policy-note",
                "license_scope": "TikTok organic and commercial",
                "verified_by": "editor",
            }
        ],
    )
    assert changed["quality"]["assets_with_verified_rights"] == 1
    assert changed["quality"]["ready_to_publish"] == 0
    assert (
        next(a for a in changed["asset_bank"] if a["asset_id"] == aid)["safe_to_publish"] is False
    )
    assert audit_production_kit(changed)["status"] == "pass"


def test_first_party_results_are_not_claimed_as_operator_success() -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
        recipes_limit=2,
    )
    changed = attach_own_experiment_outcomes(
        kit,
        [
            {
                "recipe_id": kit["recipes"][0]["recipe_id"],
                "account_slot": "PILOT-A",
                "published_url": "https://www.tiktok.com/@myaccount/video/123",
                "views": "1000",
                "account_median_views": "400",
                "saves": "14",
                "shares": "4",
                "notes": "Original creative, one test only",
            },
        ],
    )
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
        **original,
        "post_uid": "P4",
        "account_id": "Beta",
        "account": "beta",
        "post_id": "444",
        "url": "https://www.tiktok.com/@beta/video/444",
    }
    evidence["posts"].append(cloned)
    families["families"].append(
        {
            "family_id": "F3",
            "member_count": 1,
            "family_origin_post_uid": "P4",
            "core_hook_text": "Study schedules for different students",
            "members": [{"post_uid": "P4"}],
        }
    )
    families["families"].append(
        {
            "family_id": "F4",
            "member_count": 1,
            "family_origin_post_uid": "P1",
            "core_hook_text": "Study schedules for different students",
            "members": [{"post_uid": "P1"}],
        }
    )
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
        recipes_limit=3,
    )
    candidates = kit["suspected_false_splits"]
    assert any({c["family_a"], c["family_b"]} == {"F3", "F4"} for c in candidates)
    assert all(c["validated_same_concept"] is False for c in candidates)


def test_orphan_reference_and_false_rights_fail_quality_gate() -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
    )
    kit["recipes"][0]["observed_source_posts"][0]["post_uid"] = "ORPHAN"
    assert "orphan_post_reference" in "|".join(
        audit_production_kit(kit, {"P1", "P2", "P3"})["errors"]
    )
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
    )
    kit["asset_bank"][0]["safe_to_publish"] = True
    assert "unlicensed_asset_marked_publishable" in "|".join(audit_production_kit(kit)["errors"])


def test_raw_enrichment_covers_unselected_posts_and_keeps_music_unlicensed(
    tmp_path: Path,
) -> None:
    """Full observed bank ≠ only best-family/source-post audio."""
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
        recipes_limit=1,
        calendar_days=3,
    )
    assert len(kit["recipes"]) == 1
    raw_dir = tmp_path / "raw" / "raw"
    raw_dir.mkdir(parents=True)
    rows = [
        {
            "id": "111",
            "input": "alpha",
            "text": "Study plans caption",
            "hashtags": [{"name": "study"}],
            "musicMeta": {
                "musicId": "SND1",
                "musicName": "Instrumental A",
                "musicAuthor": "Artist A",
            },
        },
        {
            "id": "333",
            "input": "alpha",
            "text": "Revision approach",
            "hashtags": [{"name": "revision"}],
            "musicMeta": {
                "musicId": "SND2",
                "musicName": "Instrumental B",
                "musicAuthor": "Artist B",
            },
        },
    ]
    (raw_dir / "all_items.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    enriched = enrich_production_kit_from_raw(
        kit,
        tmp_path / "raw",
        evidence_posts=evidence["posts"],
    )
    assert enriched["quality"]["raw_posts_expected"] == 3
    assert enriched["quality"]["raw_posts_matched"] == 2
    assert {row["music_id"] for row in enriched["music_bank"]} == {"SND1", "SND2"}
    assert len(enriched["caption_bank"]) == 2
    assert {row["hashtag"] for row in enriched["hashtag_bank"]} == {"study", "revision"}
    assert all(row["usable_as_commercial_sound"] is False for row in enriched["music_bank"])
    assert all(row["rights_status"] == "not_verified" for row in enriched["asset_bank"])
    assert enriched["quality"]["ready_to_publish"] == 0
    artifacts = write_production_kit(enriched, workspace=tmp_path)
    assert artifacts["quality"]["status"] == "pass"
    with zipfile.ZipFile(tmp_path / "production-kit.zip") as z:
        assert "Instrumental B" in z.read("SOUND_BANK.csv").decode("utf-8-sig")
        assert "Revision approach" in z.read("CAPTION_BANK.csv").decode("utf-8-sig")
        assert "revision" in z.read("HASHTAG_BANK.csv").decode("utf-8-sig")


def test_operator_specific_creative_archetypes_draft_distinct_team_briefs() -> None:
    cases = [
        (
            "student_personas",
            "study schedules for different student types",
            "Study schedules for different students",
            "Categorize common user personas facing a challenge",
        ),
        (
            "schedule_myth",
            "perfect study schedule and study app recommendation",
            "El horario de estudio perfecto no existe",
            "Challenge a common belief and offer an alternative",
        ),
        (
            "subject_techniques",
            "best study techniques for each subject and app recommendation",
            "How to study for different subjects",
            "Subject-by-subject tip list",
        ),
        (
            "tips_wish_sooner",
            "study techniques",
            "Study tips I wish I knew sooner",
            "Regret hook and per-subject advice",
        ),
        (
            "knowledge_habits",
            "how to become educated and knowledgeable across any topic",
            "Cómo estar ridículamente educado",
            "Daily learning habits",
        ),
        (
            "clinical_study",
            "medication calculations every nursing student must know",
            "5 Medication Calculations",
            "Number + Topic + Audience",
        ),
    ]
    results = []
    for expected, topic, hook, formula in cases:
        subtype, title, body = _editorial_spec(
            "study_method", topic=topic, hook=hook, formula=formula
        )
        assert subtype == expected
        assert title and len(body) >= 4
        results.append((title, tuple(body)))
    assert len({x[0] for x in results}) == len(cases)
    assert "Không dùng bài đăng hoặc AI thay hướng dẫn tính liều" in (" ".join(results[-1][1]))


def test_calendar_contains_distinct_hook_variants_and_no_proven_best_time() -> None:
    evidence, families, accounts = _fixture()
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=accounts,
        recipes_limit=2,
        calendar_days=4,
    )
    plan = kit["calendar"]
    assert len(plan) == 4
    for recipe in kit["recipes"]:
        slots = [row for row in plan if row["recipe_id"] == recipe["recipe_id"]]
        assert len(slots) == 2
        assert {row["variant"] for row in slots} == {"A", "B"}
        assert len({row["hook_to_publish_draft_vi"] for row in slots}) == 2
        assert len({row["pilot_account"] for row in slots}) == 1
        assert len({row["planned_local_time"] for row in slots}) == 1
        assert all(
            row["time_basis"] == "proposed_experiment_not_validated_best_time" for row in slots
        )
        assert all(row["publish_gate"] == "blocked_until_rights_and_copy_review" for row in slots)
        assert all(row["tracking"] == "new_tracking_required" for row in slots)


def test_canonical_source_asset_index_is_reused_and_invalidated_on_raw_change(
    tmp_path: Path,
) -> None:
    import stat

    evidence, families, accounts = _fixture()
    raw = tmp_path / "raw" / "posts.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text(
        json.dumps(
            {
                "id": "111",
                "input": "alpha",
                "text": "Original public caption A",
                "hashtags": [{"name": "studytok"}],
                "musicMeta": {"musicId": "SND1", "musicName": "Study melody"},
                "secret_unused_source_field": "DO_NOT_INDEX",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cache = tmp_path / "data/05_master/source_asset_index.json"

    def fresh_kit():
        return build_production_kit(
            evidence=evidence,
            families=families,
            accounts=accounts,
            recipes_limit=2,
            calendar_days=4,
        )

    first = enrich_production_kit_from_raw(
        fresh_kit(),
        raw.parent,
        evidence_posts=evidence["posts"],
        cache_path=cache,
    )
    assert first["quality"]["raw_metadata_cache_hit"] is False
    assert cache.exists()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    cached = json.loads(cache.read_text(encoding="utf-8"))
    assert "DO_NOT_INDEX" not in json.dumps(cached)
    assert cached["license_scope"] == "reference_only_not_copyright_clearance"

    next_kit = enrich_production_kit_from_raw(
        fresh_kit(),
        raw.parent,
        evidence_posts=evidence["posts"],
        cache_path=cache,
    )
    assert next_kit["quality"]["raw_metadata_cache_hit"] is True
    assert next_kit["music_bank"] == first["music_bank"]
    assert next_kit["caption_bank"] == first["caption_bank"]

    with raw.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "id": "333",
                    "input": "alpha",
                    "text": "Additional original public caption",
                    "musicMeta": {"musicId": "SND2", "musicName": "Other sound"},
                }
            )
            + "\n"
        )
    newest = enrich_production_kit_from_raw(
        fresh_kit(),
        raw.parent,
        evidence_posts=evidence["posts"],
        cache_path=cache,
    )
    assert newest["quality"]["raw_metadata_cache_hit"] is False
    assert len(newest["music_bank"]) == 2
    assert newest["quality"]["raw_posts_matched"] == 2
    assert all(sound["usable_as_commercial_sound"] is False for sound in newest["music_bank"])
