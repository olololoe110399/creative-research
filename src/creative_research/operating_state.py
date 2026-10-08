"""Single durable creator-team operating state independent of research rebuilds.

Public operator evidence lives in immutable materialized JSON. Edits, asset
clearance, publication and own outcomes live in ONE operator-scoped private
state. A changing REC-001 / PUB-001 / AST-001 identifier cannot silently
redirect old team work to another source family after a rebuild.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class OperatingError(ValueError):
    pass


SCHEMA = "operator-operating-state-v1"
ASSET_STATES = ("needed", "sourced", "rights_checked", "editorial_checked", "ready")
SLOT_STATES = ("draft", "in_production", "ready", "published", "skipped")
ACCOUNT_STATES = ("planned", "created", "active", "retired")
MAX_TEXT = 3000
MAX_RESULTS = 2500


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, *, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise OperatingError("expected_text")
    if len(value) > limit:
        raise OperatingError("text_too_long")
    return value.strip()


def _hash(row: Any) -> str:
    return hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _valid_tiktok_post(url: str) -> bool:
    p = urlsplit(url)
    return (
        p.scheme == "https"
        and (p.hostname == "tiktok.com" or (p.hostname or "").endswith(".tiktok.com"))
        and ("/video/" in p.path or "/photo/" in p.path)
        and len(url) <= 1024
    )


def _int(value: Any, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise OperatingError("invalid_integer")
    try:
        n = int(value)
        if float(value) != n or n < minimum:
            raise OperatingError("invalid_integer")
        return n
    except (TypeError, ValueError, OverflowError) as exc:
        raise OperatingError("invalid_integer") from exc


def _family_id(recipe: dict[str, Any]) -> str:
    fid = str(recipe.get("family_id") or "")
    if not fid:
        raise OperatingError("missing_recipe_family")
    return fid


def _recipe_signature(recipe: dict[str, Any]) -> str:
    return _hash({
        "family_id": _family_id(recipe),
        "source_representative": (recipe.get("evidence") or {}).get(
            "selected_representative_uid"
        ),
        "source_posts": [
            p.get("post_uid") for p in recipe.get("observed_source_posts") or []
        ],
        "slides": [
            (s.get("role"), s.get("source_text_reference_only"),
             s.get("source_visual_description"))
            for s in recipe.get("slides") or []
        ],
    })


def _asset_key(asset: dict[str, Any], family: str) -> str:
    return f"{family}|{asset.get('kind')}|{asset.get('role')}"


def _slot_signature(slot: dict[str, Any], family: str) -> str:
    return _hash({
        "family_id": family,
        "account": slot.get("pilot_account"),
        "day": slot.get("day"),
        "variant": slot.get("variant"),
        "hook": slot.get("hook_to_publish_draft_vi"),
    })


def _json_from(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OperatingError(f"corrupt_data:{path.name}") from exc
    if not isinstance(value, dict):
        raise OperatingError(f"invalid_data:{path.name}")
    return value


def _dict_rows(rows: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise OperatingError(f"invalid_rows:{key}")
    found = {}
    for value in rows:
        if not isinstance(value, dict) or not value.get(key):
            raise OperatingError(f"invalid_row:{key}")
        name = str(value[key])
        if name in found:
            raise OperatingError(f"duplicate:{key}:{name}")
        found[name] = value
    return found


class OperatingStore:
    """A single mutable source for creator-team work; not operator truth."""

    def __init__(
        self, workspace: Path, *, directory: Path | None = None,
        legacy_directory: Path | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.directory = (
            directory or self.workspace.parent.parent / "07_knowledge" / "operating_state"
        ).resolve()
        self.legacy_directory = (
            legacy_directory or self.workspace.parent.parent / "07_knowledge" / "experiment_plans"
        ).resolve()
        self.lock = threading.RLock()

    def _sources(self) -> dict[str, Any]:
        kit = _json_from(self.workspace / "production.json")
        lab = _json_from(self.workspace / "lab.json")
        if kit.get("schema_version") != "creator-production-kit-v1":
            raise OperatingError("invalid_production_kit")
        operator_id = str(kit.get("operator_id") or "")
        if not operator_id or lab.get("research_intelligence", {}).get("operator_id") != operator_id:
            raise OperatingError("operator_mismatch")
        recipes = _dict_rows(kit.get("recipes", []), "recipe_id")
        families: dict[str, dict[str, Any]] = {}
        for recipe in recipes.values():
            fid = _family_id(recipe)
            if fid in families:
                raise OperatingError("duplicate_family_recipe")
            families[fid] = recipe
        assets = _dict_rows(kit.get("asset_bank", []), "asset_id")
        slots = _dict_rows(kit.get("calendar", []), "slot_id")
        accounts = _dict_rows(kit.get("account_blueprints", []), "slot_id")
        for row in assets.values():
            if row.get("recipe_id") not in recipes:
                raise OperatingError("orphan_asset_source")
        for row in slots.values():
            if row.get("recipe_id") not in recipes:
                raise OperatingError("orphan_slot_source")
        return {
            "operator_id": operator_id,
            "kit": kit,
            "recipes": recipes, "families": families,
            "assets": assets, "slots": slots, "accounts": accounts,
        }

    def _path(self, operator_id: str) -> Path:
        digest = hashlib.sha256(operator_id.encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{digest}.json"

    def _legacy(self, operator_id: str) -> list[dict[str, Any]]:
        path = self.legacy_directory / self._path(operator_id).name
        if not path.is_file():
            return []
        old = _json_from(path)
        if (old.get("schema_version") != "experiment-plan-v1"
                or old.get("operator_id") != operator_id
                or not isinstance(old.get("items"), dict)):
            raise OperatingError("legacy_experiment_plan_corrupt")
        return [
            {"key": key, **record, "migrated_from": "experiment-plan-v1",
             "source": "legacy_hypothesis_experiment_not_production_recipe"}
            for key, record in sorted(old["items"].items())
            if isinstance(record, dict)
        ]

    def _load(self, operator_id: str) -> dict[str, Any]:
        path = self._path(operator_id)
        if path.exists():
            doc = _json_from(path)
            if (
                doc.get("schema_version") != SCHEMA or
                doc.get("operator_id") != operator_id or
                not all(isinstance(doc.get(k), dict) for k in (
                    "recipes", "assets", "slots", "accounts", "outcomes",
                )) or
                not isinstance(doc.get("legacy_experiments"), list)
            ):
                raise OperatingError("operating_state_wrong_operator_or_schema")
            doc.setdefault("source_migrations",[])
            return doc
        return {
            "schema_version": SCHEMA,
            "operator_id": operator_id,
            "created_at": _now(),
            "revision": 0,
            "recipes": {},
            "assets": {},
            "slots": {},
            "accounts": {},
            "outcomes": {},
            "legacy_experiments": self._legacy(operator_id),
            "source_migrations": [],
            "migration": "legacy_read_only_experiment_history_imported_once",
        }

    def _save(self, operator_id: str, state: dict[str, Any]) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(operator_id)
        # No interrupted rebuild or corrupted CSV can partially update the file.
        fd, name = tempfile.mkstemp(prefix=".operating-", suffix=".json",dir=self.directory)
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                os.fchmod(fh.fileno(), 0o600)
                json.dump(state, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _snapshot(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": item.get("state", item.get("status")),
            "owner": item.get("owner") or "",
            "notes": item.get("notes") or "",
            "updated_at": item.get("updated_at"),
        }

    @staticmethod
    def _current_item(
        saved: dict[str, Any] | None,
        fingerprint: str,
    ) -> dict[str, Any]:
        if saved is None:
            return {"state": "not_started", "needs_recheck": False}
        return {
            **saved,
            "needs_recheck": saved.get("source_signature") != fingerprint,
        }

    def _view_unlocked(
        self, sources: dict[str, Any], state: dict[str, Any],
    ) -> dict[str, Any]:
        recipes = sources["recipes"]
        families = sources["families"]
        original_assets = sources["assets"]
        original_slots = sources["slots"]
        recipe_by_id = {
            rid: families[_family_id(row)] for rid, row in recipes.items()
        }
        recipe_items = []
        for family, row in families.items():
            saved = state["recipes"].get(family)
            signature = _recipe_signature(row)
            recipe_items.append({
                "family_id": family,
                "recipe_id": row["recipe_id"],
                "title": row.get("title"),
                "source_signature": signature,
                **self._current_item(saved,signature),
            })
        asset_items = []
        current_asset_keys = set()
        for asset in original_assets.values():
            fam = _family_id(recipe_by_id[asset["recipe_id"]])
            aid = _asset_key(asset,fam)
            current_asset_keys.add(aid)
            signature = _recipe_signature(families[fam])
            saved = state["assets"].get(aid)
            asset_items.append({
                "asset_key": aid,
                "asset_id": asset["asset_id"],
                "family_id": fam,
                "kind": asset.get("kind"),
                "role": asset.get("role"),
                "source_signature": signature,
                **self._current_item(saved,signature),
            })
        slot_items = []
        current_slot_keys = set()
        for slot in original_slots.values():
            fam = _family_id(recipe_by_id[slot["recipe_id"]])
            key = str(slot["slot_id"])
            current_slot_keys.add(key)
            signature = _slot_signature(slot,fam)
            saved = state["slots"].get(key)
            slot_items.append({
                "slot_id": key,
                "recipe_id": slot["recipe_id"],
                "family_id": fam,
                "source_signature": signature,
                **self._current_item(saved,signature),
            })
        accounts = [{
            "slot_id": key,
            **self._current_item(
                state["accounts"].get(key),
                _hash(row),
            ),
        } for key, row in sources["accounts"].items()]
        stale = {
            "recipes": [k for k in state["recipes"] if k not in families],
            "assets": [k for k in state["assets"] if k not in current_asset_keys],
            "slots": [k for k in state["slots"] if k not in current_slot_keys],
            "outcomes": [
                key for key, outcome in state["outcomes"].items()
                if outcome.get("slot_id") not in current_slot_keys
            ],
        }
        stale_count = sum(len(value) for value in stale.values()) + sum(
            bool(item.get("needs_recheck"))
            for item in recipe_items+asset_items+slot_items+accounts
        )
        return {
            "schema_version": SCHEMA,
            "operator_id": sources["operator_id"],
            "revision": state["revision"],
            "recipe_work": recipe_items,
            "asset_work": asset_items,
            "slot_work": slot_items,
            "account_work": accounts,
            "outcomes": sorted(
                state["outcomes"].values(),
                key=lambda r: (r.get("recorded_at", ""),r.get("outcome_id", "")),
            ),
            "legacy_experiments": state["legacy_experiments"],
            "source_migrations_count": len(state["source_migrations"]),
            "stale_work": stale,
            "stale_count": stale_count,
            "source_fingerprint": sources["kit"].get("source_fingerprint"),
            "source": (
                "Independent first-party team work; NOT certification "
                "of an external operator's internal decisions."
            ),
        }

    def view(self) -> dict[str, Any]:
        sources = self._sources()
        with self.lock:
            state = self._load(sources["operator_id"])
            return self._view_unlocked(sources,state)

    def _find_asset(
        self, sources: dict[str, Any], key: str,
    ) -> tuple[dict[str, Any], str]:
        for asset in sources["assets"].values():
            family = _family_id(sources["recipes"][asset["recipe_id"]])
            if _asset_key(asset,family) == key:
                return asset,_recipe_signature(sources["families"][family])
        raise OperatingError("unknown_asset")

    def _find_slot(
        self, sources: dict[str, Any], slot_id: str,
    ) -> tuple[dict[str, Any], str, str]:
        slot = sources["slots"].get(slot_id)
        if slot is None:
            raise OperatingError("unknown_slot")
        fam = _family_id(sources["recipes"][slot["recipe_id"]])
        return slot,fam,_slot_signature(slot,fam)

    def mutate(self, payload: dict[str, Any]) -> dict[str, Any]:
        sources = self._sources()
        action = _text(payload.get("action",""),limit=40)
        name = _text(payload.get("key",""),limit=180)
        revision = payload.get("expected_revision")
        if not isinstance(revision, int) or isinstance(revision,bool):
            raise OperatingError("expected_revision_required")
        with self.lock:
            state = self._load(sources["operator_id"])
            if revision != state["revision"]:
                raise OperatingError("stale_revision_reload_required")
            now = _now()
            if action == "recipe":
                family = name
                row = sources["families"].get(family)
                if row is None:
                    raise OperatingError("unknown_recipe_family")
                signature = _recipe_signature(row)
                old = state["recipes"].get(family)
                if old and old.get("source_signature") != signature:
                    raise OperatingError("source_changed_recheck_required")
                state["recipes"][family] = {
                    "family_id": family,
                    "source_signature": signature,
                    "state": "edited",
                    "edited_hook": _text(payload.get("edited_hook",""),limit=1200),
                    "edited_caption": _text(payload.get("edited_caption",""),limit=2500),
                    "notes": _text(payload.get("notes","")),
                    "editorial_checked_by": _text(
                        payload.get("editorial_checked_by",""),limit=120
                    ),
                    "updated_at": now,
                }
            elif action == "account":
                row = sources["accounts"].get(name)
                if row is None:
                    raise OperatingError("unknown_account_slot")
                status = _text(payload.get("state",""),limit=30)
                if status not in ACCOUNT_STATES:
                    raise OperatingError("invalid_account_state")
                handle = _text(payload.get("handle",""),limit=80)
                if status in {"created","active"} and not re.fullmatch(
                    r"@?[A-Za-z0-9_.]{1,32}",handle,
                ):
                    raise OperatingError("created_account_requires_owned_handle")
                old = state["accounts"].get(name)
                if old and old.get("source_signature") != _hash(row):
                    raise OperatingError("source_changed_recheck_required")
                state["accounts"][name] = {
                    "slot_id": name,
                    "source_signature": _hash(row),
                    "state": status,
                    "handle": handle,
                    "notes": _text(payload.get("notes","")),
                    "updated_at": now,
                }
            elif action == "asset":
                row, signature = self._find_asset(sources,name)
                requested = _text(payload.get("state",""),limit=35)
                if requested not in ASSET_STATES:
                    raise OperatingError("invalid_asset_state")
                old = state["assets"].get(name)
                if old and old.get("source_signature") != signature:
                    raise OperatingError("source_changed_recheck_required")
                prev = old.get("state","needed") if old else "needed"
                if requested != prev and abs(
                    ASSET_STATES.index(requested)-ASSET_STATES.index(prev)
                ) > 1 and ASSET_STATES.index(requested) > ASSET_STATES.index(prev):
                    raise OperatingError("cannot_skip_asset_quality_gate")
                location = _text(payload.get("location",""),limit=1500)
                evidence = _text(payload.get("license_evidence",""),limit=1500)
                scope = _text(payload.get("license_scope",""),limit=600)
                reviewer = _text(payload.get("rights_checked_by",""),limit=120)
                editor = _text(payload.get("editorial_checked_by",""),limit=120)
                # Only an identified team member can assert rights or
                # approve original brand copy, and both must be explicit.
                if requested in {"rights_checked","editorial_checked","ready"}:
                    if not all((location,evidence,scope,reviewer)):
                        raise OperatingError("rights_evidence_required")
                    if "tiktok" not in scope.casefold():
                        raise OperatingError("target_platform_rights_scope_required")
                if requested in {"editorial_checked","ready"} and not editor:
                    raise OperatingError("editorial_reviewer_required")
                state["assets"][name] = {
                    "asset_key": name,
                    "asset_id": row["asset_id"],
                    "source_signature": signature,
                    "state": requested,
                    "location": location, "license_evidence": evidence,
                    "license_scope": scope, "rights_checked_by": reviewer,
                    "editorial_checked_by": editor,
                    "notes": _text(payload.get("notes","")),
                    "updated_at": now,
                    "verified_by_team_not_independent_license_counsel": True,
                }
            elif action == "slot":
                slot,family,signature = self._find_slot(sources,name)
                requested = _text(payload.get("state",""),limit=35)
                if requested not in SLOT_STATES:
                    raise OperatingError("invalid_slot_state")
                old = state["slots"].get(name)
                if old and old.get("source_signature") != signature:
                    raise OperatingError("source_changed_recheck_required")
                owner = _text(payload.get("owner",""),limit=120)
                url = _text(payload.get("published_url",""),limit=1024)
                when = _text(payload.get("published_at",""),limit=60)
                if requested in {"ready","published"}:
                    recipe_state = state["recipes"].get(family) or {}
                    if (recipe_state.get("source_signature") != _recipe_signature(
                        sources["families"][family]
                    ) or not recipe_state.get("editorial_checked_by")):
                        raise OperatingError("recipe_copy_editorial_review_required")
                    for asset in sources["assets"].values():
                        if asset["recipe_id"] == slot["recipe_id"]:
                            asset_key = _asset_key(asset,family)
                            rec = state["assets"].get(asset_key) or {}
                            if rec.get("source_signature") != _recipe_signature(
                                sources["families"][family]
                            ) or rec.get("state") != "ready":
                                raise OperatingError("all_recipe_assets_must_be_ready")
                if requested == "published":
                    if not _valid_tiktok_post(url) or not when:
                        raise OperatingError("published_requires_tiktok_url_and_date")
                state["slots"][name] = {
                    "slot_id": name,"family_id": family,
                    "source_signature": signature,
                    "state": requested,
                    "owner": owner,"published_url": url,"published_at": when,
                    "notes": _text(payload.get("notes","")),
                    "updated_at": now,
                }
            elif action == "outcome":
                slot,family,signature = self._find_slot(sources,name)
                published = state["slots"].get(name) or {}
                if (published.get("source_signature") != signature
                        or published.get("state") != "published"):
                    raise OperatingError("publish_before_recording_outcome")
                age = _int(payload.get("age_hours"),minimum=1)
                if age not in {24,72,168}:
                    raise OperatingError("invalid_measurement_age")
                views = _int(payload.get("views"),minimum=0)
                saves = _int(payload.get("saves"),minimum=0)
                shares = _int(payload.get("shares"),minimum=0)
                baseline = _int(payload.get("age_matched_baseline"),minimum=1)
                outcome_id = f"{name}:{age}"
                record = {
                    "outcome_id": outcome_id, "slot_id": name,
                    "recipe_id_at_publication": slot["recipe_id"],
                    "family_id_at_publication": family,
                    "source_signature": signature,
                    "published_url": published["published_url"],
                    "age_hours": age,
                    "views": views,"saves": saves,"shares": shares,
                    "age_matched_baseline": baseline,
                    "views_vs_baseline": round(views/baseline,3),
                    "saves_per_view": round(saves/views,6) if views else None,
                    "shares_per_view": round(shares/views,6) if views else None,
                    "notes": _text(payload.get("notes","")),
                    "recorded_at": now,
                    "evidence_origin": "first_party_team_entered",
                    "causal_claim": False,
                }
                history = (state["outcomes"].get(outcome_id) or {}).get("history",[])
                if outcome_id in state["outcomes"]:
                    previous = dict(state["outcomes"][outcome_id])
                    previous.pop("history",None)
                    history = [*history,previous][-25:]
                record["history"] = history
                if len(state["outcomes"]) >= MAX_RESULTS and outcome_id not in state["outcomes"]:
                    raise OperatingError("too_many_results")
                state["outcomes"][outcome_id] = record
            elif action == "recheck":
                if payload.get("confirm_source_change") is not True:
                    raise OperatingError("explicit_source_recheck_required")
                category = _text(payload.get("category",""),limit=20)
                if category == "recipe":
                    row = sources["families"].get(name)
                    fingerprint = _recipe_signature(row) if row else ""
                    collection = "recipes"
                elif category == "asset":
                    _,fingerprint = self._find_asset(sources,name)
                    collection = "assets"
                elif category == "slot":
                    _,_,fingerprint = self._find_slot(sources,name)
                    collection = "slots"
                elif category == "account":
                    row = sources["accounts"].get(name)
                    fingerprint = _hash(row) if row else ""
                    collection = "accounts"
                else:
                    raise OperatingError("invalid_recheck_category")
                old = state[collection].get(name)
                if not old or not fingerprint:
                    raise OperatingError("missing_source_to_recheck")
                if old.get("source_signature") == fingerprint:
                    raise OperatingError("source_did_not_change")
                if len(state["source_migrations"]) >= 1000:
                    raise OperatingError("migration_history_full_backup_required")
                state["source_migrations"].append({
                    "category":category, "key":name,
                    "old_work_snapshot":dict(old),
                    "new_source_signature":fingerprint,
                    "rechecked_at":now,
                    "research_internal_intent_not_approved":True,
                })
                updated = dict(old)
                updated["source_signature"] = fingerprint
                updated["updated_at"] = now
                if category == "recipe":
                    updated["editorial_checked_by"] = ""
                    updated["state"] = "edited"
                elif category == "asset":
                    updated.update({
                        "state":"needed", "location":"",
                        "license_evidence":"", "license_scope":"",
                        "rights_checked_by":"", "editorial_checked_by":"",
                    })
                elif category == "slot":
                    updated.update({
                        "state":"draft", "published_url":"", "published_at":"",
                    })
                else:
                    updated["state"]="planned"
                state[collection][name] = updated
            else:
                raise OperatingError("invalid_operating_action")
            state["revision"] += 1
            state["updated_at"] = now
            self._save(sources["operator_id"],state)
            return self._view_unlocked(sources,state)

    def export_zip(self) -> bytes:
        """Include live team edits/results without mutating canonical evidence."""
        sources = self._sources()
        with self.lock:
            state = self._load(sources["operator_id"])
            snapshot = self._view_unlocked(sources,state)
        from creative_research.production_kit import production_kit_artifacts

        def csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
            buff = io.StringIO(newline="")
            writer = csv.DictWriter(buff,fieldnames=columns,extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key:json.dumps(row.get(key),ensure_ascii=False)
                    if isinstance(row.get(key),(list,dict)) else row.get(key)
                    for key in columns
                })
            return buff.getvalue().encode("utf-8-sig")

        allfiles = production_kit_artifacts(sources["kit"])
        allfiles["TEAM_STATE.json"] = json.dumps(
            snapshot,ensure_ascii=False,indent=2
        ).encode("utf-8")
        allfiles["TEAM_OWN_OUTCOMES.csv"] = csv_bytes(
            snapshot["outcomes"],
            ["outcome_id","slot_id","recipe_id_at_publication",
             "family_id_at_publication","published_url","age_hours",
             "views","saves","shares","age_matched_baseline",
             "views_vs_baseline","saves_per_view","shares_per_view",
             "notes","recorded_at","evidence_origin"],
        )
        allfiles["TEAM_TASKS.csv"] = csv_bytes(
            [{"kind":kind,**r} for kind,records in [
                ("recipe",snapshot["recipe_work"]),
                ("slot",snapshot["slot_work"]),
                ("asset",snapshot["asset_work"]),
                ("account",snapshot["account_work"]),
            ] for r in records],
            ["kind","family_id","recipe_id","asset_key","asset_id","slot_id",
             "state","needs_recheck","owner","notes","updated_at"],
        )
        allfiles["TEAM_README.txt"] = (
            "Team-edited working state is in TEAM_STATE.json and TEAM_TASKS.csv.\n"
            "Original source research is immutable; rights and publication are "
            "human-operational tasks, not certification of operator intent.\n"
            "Changed source families or publishing plans show needs_recheck.\n"
        ).encode()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as zf:
            for name,content in sorted(allfiles.items()):
                zf.writestr(name,content)
        return buffer.getvalue()


    def import_first_party_csv(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        """Atomic import into the SAME store as UI results, never production.json."""
        sources = self._sources()
        recipes = sources["recipes"]
        accounts = sources["accounts"]
        if len(rows) > MAX_RESULTS:
            raise OperatingError("csv_results_limit_exceeded")
        prepared: dict[str, dict[str, Any]] = {}
        for i,row in enumerate(rows,1):
            if not isinstance(row,dict):
                raise OperatingError(f"invalid_result_row:{i}")
            rid = _text(row.get("recipe_id",""),limit=90)
            source = recipes.get(rid)
            if source is None:
                raise OperatingError(f"unknown_csv_recipe:{rid}")
            account = _text(row.get("account_slot",""),limit=90)
            if account not in accounts:
                raise OperatingError(f"unknown_csv_owned_account:{account}")
            url = _text(row.get("published_url",""),limit=1024)
            if not _valid_tiktok_post(url):
                raise OperatingError(f"invalid_csv_tiktok_post:{i}")
            date = _text(row.get("posted_at",""),limit=60)
            try:
                parsed = datetime.fromisoformat(date.replace("Z","+00:00"))
            except ValueError as exc:
                raise OperatingError(f"invalid_csv_published_time:{i}") from exc
            if parsed.tzinfo is None:
                raise OperatingError(f"csv_published_time_requires_offset:{i}")
            age = _int(row.get("measurement_age_hours"),minimum=1)
            if age not in {24,72,168}:
                raise OperatingError(f"invalid_csv_post_age:{i}")
            views = _int(row.get("views"),minimum=0)
            saves = _int(row.get("saves"),minimum=0)
            shares = _int(row.get("shares"),minimum=0)
            baseline = _int(row.get("account_median_views"),minimum=1)
            family = _family_id(source)
            oid = "import:"+_hash((family,url,age))[:26]
            if oid in prepared:
                raise OperatingError(f"duplicate_csv_result:{i}")
            prepared[oid] = {
                "outcome_id":oid,
                "slot_id":None,
                "account_slot":account,
                "recipe_id_at_publication":rid,
                "family_id_at_publication":family,
                "source_signature":_recipe_signature(source),
                "published_url":url,
                "posted_at":date,
                "age_hours":age,
                "views":views,"saves":saves,"shares":shares,
                "age_matched_baseline":baseline,
                "views_vs_baseline":round(views/baseline,3),
                "saves_per_view":round(saves/views,6) if views else None,
                "shares_per_view":round(shares/views,6) if views else None,
                "notes":_text(row.get("notes",""),limit=800),
                "evidence_origin":"first_party_user_csv_import",
                "causal_claim":False,
                "result_not_linked_to_publishing_slot":True,
                "recorded_at":_now(),
            }
        with self.lock:
            state = self._load(sources["operator_id"])
            for oid,item in prepared.items():
                history=(state["outcomes"].get(oid) or {}).get("history",[])
                if oid in state["outcomes"]:
                    previous=dict(state["outcomes"][oid])
                    previous.pop("history",None)
                    history=[*history,previous][-25:]
                item["history"]=history
            if len(set(state["outcomes"])|set(prepared)) > MAX_RESULTS:
                raise OperatingError("too_many_results")
            state["outcomes"].update(prepared)
            if prepared:
                state["revision"] += 1
                state["updated_at"] = _now()
                self._save(sources["operator_id"],state)
            return self._view_unlocked(sources,state)

    def import_asset_attestations(self,rows: list[dict[str,str]]) -> dict[str,Any]:
        """Import actual team rights CSV atomically; never self-authorize publishing."""
        sources=self._sources()
        recipes=sources["recipes"]
        prepared={}
        seen=set()
        for row in rows:
            asset_id=_text(row.get("asset_id",""),limit=90)
            if asset_id in seen:
                raise OperatingError("duplicate_csv_asset")
            seen.add(asset_id)
            asset=sources["assets"].get(asset_id)
            if asset is None:
                raise OperatingError("unknown_csv_asset")
            status=_text(row.get("rights_status",""),limit=40)
            if status != "team_attested_licensed":
                raise OperatingError("csv_rights_must_be_team_attested_licensed")
            family=_family_id(recipes[asset["recipe_id"]])
            key=_asset_key(asset,family)
            location=_text(row.get("file_or_licensed_source_url",""),limit=1500)
            license_evidence=_text(row.get("license_evidence_url",""),limit=1500)
            scope=_text(row.get("license_scope",""),limit=600)
            reviewer=_text(row.get("verified_by",""),limit=120)
            if not all((location,license_evidence,scope,reviewer)):
                raise OperatingError("rights_evidence_required")
            if "tiktok" not in scope.casefold():
                raise OperatingError("target_platform_rights_scope_required")
            prepared[key]={
                "asset_key":key,"asset_id":asset_id,
                "source_signature":_recipe_signature(sources["families"][family]),
                "state":"rights_checked",
                "location":location,"license_evidence":license_evidence,
                "license_scope":scope,"rights_checked_by":reviewer,
                "editorial_checked_by":"",
                "notes":"Imported from team rights attestation CSV; editorial review pending.",
                "updated_at":_now(),
                "verified_by_team_not_independent_license_counsel":True,
            }
        with self.lock:
            state=self._load(sources["operator_id"])
            for key,item in prepared.items():
                previous=state["assets"].get(key)
                if previous and previous.get("source_signature")!=item["source_signature"]:
                    raise OperatingError("source_changed_recheck_required")
            state["assets"].update(prepared)
            if prepared:
                state["revision"] += 1
                state["updated_at"]=_now()
                self._save(sources["operator_id"],state)
            return self._view_unlocked(sources,state)
