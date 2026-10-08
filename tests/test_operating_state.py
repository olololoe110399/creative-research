from __future__ import annotations

import http.server
import json
import io
import stat
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from creative_research.operating_state import OperatingError, OperatingStore
from creative_research.production_kit import build_production_kit, write_production_kit
from creative_research.stages.intelligence import _make_handler


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "data/07_exports/operator-intelligence"
    root.mkdir(parents=True)
    def post(uid: str, handle: str):
        return {
            "post_uid": uid, "operator_id": "OP1",
            "account_id": handle.upper(), "account": handle, "post_id": uid,
            "url": f"https://www.tiktok.com/@{handle}/video/{uid}",
            "content_type": "slideshow", "views": 1000,
            "performance": {"views_percentile_account": .5},
            "creative": {"topic": "study schedules", "hook_text": "4 study schedules",
                         "content_angle": "study_method"},
            "sequence": [
                {"position": 1, "role": "hook", "primary_text": "Student schedule",
                 "visual_description": "Owned desk photo", "visual_type": "study_desk_photo"},
                {"position": 2, "role": "body", "primary_text": "Morning routine",
                 "visual_description": "Owned planner", "visual_type": "study_desk_photo"},
            ],
        }
    evidence={"posts":[post("100","alpha"),post("200","beta")]}
    fam={"family_id":"F1","member_count":2,"cross_account":True,
         "core_topic":"study schedules","core_hook_text":"4 study schedules",
         "members":[{"post_uid":"100"},{"post_uid":"200"}]}
    family={"families":[fam]}
    accounts={"accounts":[{"operator_id":"OP1","account_id":"ALPHA",
                           "account":"alpha","observed_posts":1},
                          {"operator_id":"OP1","account_id":"BETA",
                           "account":"beta","observed_posts":1}]}
    kit=build_production_kit(
        evidence=evidence, families=family, accounts=accounts,
        recipes_limit=1,calendar_days=2,
    )
    write_production_kit(kit,workspace=root)
    (root/"lab.json").write_text(
        json.dumps({"research_intelligence":{"operator_id":"OP1"}}),encoding="utf-8"
    )
    return root


def _act(store: OperatingStore, **patch: object) -> dict:
    revision=store.view()["revision"]
    return store.mutate({"expected_revision":revision,**patch})


def _asset_ready(store: OperatingStore, key: str) -> None:
    data=dict(
        key=key,location="owned/photo.png",
        license_evidence="signed-creator-photo-log",
        license_scope="TikTok organic and commercial",
        rights_checked_by="legal-reviewer",
        editorial_checked_by="team-editor",
        notes="original asset",
    )
    for state in ("sourced","rights_checked","editorial_checked","ready"):
        _act(store,action="asset",state=state,**data)


def test_private_persistent_state_survives_rebuilding_read_only_research(
    tmp_path: Path,
) -> None:
    workspace=_workspace(tmp_path)
    store=OperatingStore(workspace)
    initial=store.view()
    assert initial["revision"] == 0
    assert initial["outcomes"] == []
    assert len(initial["recipe_work"]) == 1
    _act(store,action="recipe",key="F1",edited_hook="Original hook written by us",
         edited_caption="Owned caption",editorial_checked_by="editor",
         notes="Do not copy operator")
    _act(store,action="account",key="PILOT-A",state="created",
         handle="@own_study",notes="secured with 2FA")
    key=store.view()["asset_work"][0]["asset_key"]
    _act(store,action="asset",key=key,state="sourced",location="owned/a.jpg",
         notes="original photo")
    private=store._path("OP1")
    assert private.is_file()
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert "operating_state" in private.parts
    assert workspace not in private.parents
    assert store.view()["recipe_work"][0]["edited_hook"] == "Original hook written by us"
    assert store.view()["account_work"][0]["handle"] == "@own_study"
    revision=store.view()["revision"]
    # Materializing the exact same research snapshot must not affect private team work.
    kit=json.loads((workspace/"production.json").read_text(encoding="utf-8"))
    write_production_kit(kit,workspace=workspace)
    reloaded=OperatingStore(workspace)
    assert reloaded.view()["revision"] == revision
    assert reloaded.view()["recipe_work"][0]["edited_hook"] == "Original hook written by us"
    assert reloaded.view()["asset_work"][0]["state"] == "sourced"


def test_optimistic_versioning_and_source_reorder_are_fail_closed(tmp_path: Path) -> None:
    workspace=_workspace(tmp_path)
    store=OperatingStore(workspace)
    _act(store,action="recipe",key="F1",edited_hook="Keep our draft",
         edited_caption="Caption",editorial_checked_by="editor",notes="Original")
    with pytest.raises(OperatingError,match="stale_revision_reload_required"):
        store.mutate({"action":"account","key":"PILOT-A","state":"planned",
                      "expected_revision":0})
    kit_path=workspace/"production.json"
    kit=json.loads(kit_path.read_text(encoding="utf-8"))
    # Renumber positional REC-001; keep family ID and evidence invariant.
    kit["recipes"][0]["recipe_id"]="REC-999"
    for row in kit["asset_bank"]:
        row["recipe_id"]="REC-999"
    for row in kit["calendar"]:
        row["recipe_id"]="REC-999"
    kit_path.write_text(json.dumps(kit),encoding="utf-8")
    assert store.view()["recipe_work"][0]["edited_hook"] == "Keep our draft"
    assert store.view()["recipe_work"][0]["needs_recheck"] is False
    # Genuine evidence change requires explicit recheck, NEVER silent transfer.
    kit["recipes"][0]["observed_source_posts"][0]["post_uid"]="CHANGED"
    kit_path.write_text(json.dumps(kit),encoding="utf-8")
    changed=store.view()
    assert changed["recipe_work"][0]["needs_recheck"]
    assert changed["stale_count"] > 0
    with pytest.raises(OperatingError,match="source_changed_recheck_required"):
        _act(store,action="recipe",key="F1",edited_hook="overwrite without recheck",
             edited_caption="Bad",editorial_checked_by="editor",notes="")


def test_rights_editorial_and_publish_cannot_be_bypassed(tmp_path: Path) -> None:
    store=OperatingStore(_workspace(tmp_path))
    asset_keys=[row["asset_key"] for row in store.view()["asset_work"]]
    slot_id=store.view()["slot_work"][0]["slot_id"]
    with pytest.raises(OperatingError,match="cannot_skip_asset_quality_gate"):
        _act(store,action="asset",key=asset_keys[0],state="ready",
             rights_checked_by="editor",editorial_checked_by="editor")
    with pytest.raises(OperatingError,match="recipe_copy_editorial_review_required"):
        _act(store,action="slot",key=slot_id,state="ready",owner="team")
    _act(store,action="recipe",key="F1",edited_hook="Our own",
         edited_caption="Original",editorial_checked_by="editor",notes="")
    with pytest.raises(OperatingError,match="all_recipe_assets_must_be_ready"):
        _act(store,action="slot",key=slot_id,state="ready",owner="team")
    for key in asset_keys:
        _asset_ready(store,key)
    _act(store,action="slot",key=slot_id,state="ready",owner="team",
         published_url="",published_at="",notes="ready, not published")
    with pytest.raises(OperatingError,match="published_requires_tiktok_url"):
        _act(store,action="slot",key=slot_id,state="published",owner="team",
             published_url="https://attacker.invalid/phishing",
             published_at="2026-10-09T10:00:00+07:00",notes="")
    url="https://www.tiktok.com/@our_account/video/99123"
    _act(store,action="slot",key=slot_id,state="published",owner="team",
         published_url=url,published_at="2026-10-09T10:00:00+07:00",notes="")
    outcome=_act(store,action="outcome",key=slot_id,age_hours="24",
                 views="500",saves="17",shares="5",age_matched_baseline="400",
                 notes="no internal operator causation claim")
    row=outcome["outcomes"][0]
    assert row["views_vs_baseline"] == 1.25
    assert row["evidence_origin"] == "first_party_team_entered"
    assert row["causal_claim"] is False
    with pytest.raises(OperatingError,match="invalid_measurement_age"):
        _act(store,action="outcome",key=slot_id,age_hours="2",
             views="100",saves="0",shares="0",age_matched_baseline="50",notes="")
    _act(store,action="outcome",key=slot_id,age_hours="24",
         views="520",saves="18",shares="5",age_matched_baseline="400",
         notes="corrected count")
    assert len(store.view()["outcomes"][0]["history"])==1
    assert store.view()["outcomes"][0]["history"][0]["views"]==500
    with zipfile.ZipFile(io.BytesIO(store.export_zip())) as z:
        assert z.testzip() is None
        assert "TEAM_STATE.json" in z.namelist()
        assert "TEAM_OWN_OUTCOMES.csv" in z.namelist()
        assert b"520" in z.read("TEAM_OWN_OUTCOMES.csv")
        assert b"our_account" in z.read("TEAM_STATE.json")


def test_legacy_experiment_history_migrates_read_only_without_clobbering(
    tmp_path: Path,
) -> None:
    workspace=_workspace(tmp_path)
    store=OperatingStore(workspace)
    legacy=store.legacy_directory/store._path("OP1").name
    legacy.parent.mkdir(parents=True,exist_ok=True)
    legacy.write_text(json.dumps({
        "schema_version":"experiment-plan-v1","operator_id":"OP1",
        "items":{"explore":{"key":"explore","state":"evaluated",
                "notes":"Previously tested, do not lose this result",
                "metric_observed":"Account median 0.6"}},
    }),encoding="utf-8")
    assert store.view()["legacy_experiments"][0]["state"] == "evaluated"
    _act(store,action="account",key="PILOT-A",state="planned",
         handle="",notes="first live edit")
    legacy.unlink()  # migration is durable in the only live store
    assert store.view()["legacy_experiments"][0]["notes"].startswith("Previously tested")


def test_operator_scope_must_not_leak_into_another_project(tmp_path: Path) -> None:
    workspace=_workspace(tmp_path)
    store=OperatingStore(workspace)
    _act(store,action="recipe",key="F1",edited_hook="Owned idea",
         edited_caption="Owned caption",editorial_checked_by="editor",notes="")
    kit_path=workspace/"production.json"
    kit=json.loads(kit_path.read_text(encoding="utf-8"))
    kit["operator_id"]="OP2"
    kit_path.write_text(json.dumps(kit),encoding="utf-8")
    with pytest.raises(OperatingError,match="operator_mismatch"):
        store.view()


def _request(base: str, endpoint: str, payload: dict | None = None,
             headers: dict | None = None) -> tuple[int,bytes]:
    body=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(
        base+endpoint,data=body,
        headers={"Content-Type":"application/json",**(headers or {})},
    )
    try:
        with urllib.request.urlopen(req,timeout=4) as r:
            return r.status,r.read()
    except urllib.error.HTTPError as e:
        return e.code,e.read()


def test_guarded_operating_endpoints_read_only_and_live_team_export(
    tmp_path: Path,
) -> None:
    workspace=_workspace(tmp_path)
    store=OperatingStore(workspace)
    handler=_make_handler(
        root=workspace,reviews_path=tmp_path/"old_reviews.toml",
        read_only=False,media_records={},operating_service=store,
    )
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),handler)
    t=threading.Thread(target=server.serve_forever,daemon=True)
    t.start()
    url=f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status,raw=_request(url,"/api/operating")
        assert status==200
        assert json.loads(raw)["revision"]==0
        body={"action":"account","key":"PILOT-A","state":"planned",
              "handle":"","notes":"hello","expected_revision":0}
        assert _request(url,"/api/operating",body,
            {"Origin":"http://attacker.invalid"})[0]==403
        assert _request(url,"/api/operating",body,
            {"Host":"attacker.invalid"})[0]==403
        assert store.view()["revision"]==0
        status,raw=_request(url,"/api/operating",body)
        assert status==200
        assert json.loads(raw)["operating"]["revision"]==1
        status,raw=_request(url,"/api/operating",body)
        assert status==409
        assert json.loads(raw)["error"]=="stale_revision_reload_required"
        status,payload=_request(url,"/api/operating/export")
        assert status==200 and payload[:2]==b"PK"
        assert _request(url,"/api/experiments")[0]==410
    finally:
        server.shutdown();server.server_close();t.join(timeout=4)

    handler=_make_handler(
        root=workspace,reviews_path=tmp_path/"reviews.toml",
        read_only=True,media_records={},operating_service=store,
    )
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),handler)
    t=threading.Thread(target=server.serve_forever,daemon=True)
    t.start()
    try:
        url=f"http://127.0.0.1:{server.server_address[1]}"
        assert _request(url,"/api/operating")[0]==200
        assert _request(url,"/api/operating",
            {"action":"account","key":"PILOT-A","state":"planned",
             "handle":"","notes":"","expected_revision":1})[0]==403
    finally:
        server.shutdown();server.server_close();t.join(timeout=4)
