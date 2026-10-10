#!/usr/bin/env python3
"""Refresh team handoff from materialized evidence; no scrape or model calls."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from creative_research.infrastructure.paths import project_root
from creative_research.operating.state import OperatingError, OperatingStore
from creative_research.production.handoff import write_production_kit
from creative_research.production.kit import DEFAULT_DAYS, DEFAULT_RECIPES, build_production_kit
from creative_research.production.quality import audit_production_kit
from creative_research.production.sources import enrich_production_kit_from_raw


def _resolve(value: str) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing materialized Lab research: {path}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise SystemExit(f"Expected an object in {path}")
    return result


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"Missing team CSV input: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def run(
    *,
    workspace: str = "data/07_exports/operator-intelligence",
    recipes: int = DEFAULT_RECIPES,
    days: int = DEFAULT_DAYS,
    raw_root: str | None = None,
    clearance_csv: str | None = None,
    own_results_csv: str | None = None,
) -> None:

    workspace_dir = _resolve(workspace)
    evidence = _load_json(workspace_dir / "evidence.json")
    families = _load_json(workspace_dir / "families.json")
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=_load_json(workspace_dir / "accounts.json"),
        lab=_load_json(workspace_dir / "lab.json"),
        recipes_limit=recipes,
        calendar_days=days,
    )
    if raw_root:
        enrich_production_kit_from_raw(
            kit,
            _resolve(raw_root),
            evidence_posts=evidence["posts"],
            cache_path=project_root() / "data/05_master/source_asset_index.json",
        )
    audit = audit_production_kit(
        kit,
        post_ids={p["post_uid"] for p in evidence["posts"]},
        family_ids={f["family_id"] for f in families["families"]},
    )
    if audit["status"] != "pass":
        raise SystemExit("Production Kit quality failed:\n" + "\n".join(audit["errors"]))
    result = write_production_kit(kit, workspace=workspace_dir)
    # Private team state is a separate single source of truth and survives
    # future research/rebuild runs. No CSV writes into production.json.
    operating = OperatingStore(workspace_dir)
    try:
        if clearance_csv:
            operating.import_asset_attestations(_load_csv(_resolve(clearance_csv)))
        if own_results_csv:
            operating.import_first_party_csv(_load_csv(_resolve(own_results_csv)))
        state = operating.view()
    except OperatingError as exc:
        raise SystemExit(f"Operating data import rejected: {exc}") from exc
    print(
        json.dumps(
            {
                "status": "draft_handoff_ready_for_team_review",
                "output": result["handoff_zip"],
                "recipe_count": len(kit["recipes"]),
                "calendar_posts": len(kit["calendar"]),
                "sound_references_found": len(kit["music_bank"]),
                "team_assets_rights_checked": sum(
                    entry.get("state") in ("rights_checked", "editorial_checked", "ready")
                    and not entry.get("needs_recheck")
                    for entry in state["asset_work"]
                ),
                "first_party_results_saved": len(state["outcomes"]),
                "private_state_revision": state["revision"],
                "publish_ready": kit["quality"]["ready_to_publish"],
                "source_fingerprint": kit["source_fingerprint"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
