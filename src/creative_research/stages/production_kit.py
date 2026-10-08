#!/usr/bin/env python3
"""Refresh team handoff from materialized evidence; no scrape or model calls."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from creative_research.pathing import project_root
from creative_research.operating_state import OperatingStore, OperatingError
from creative_research.production_kit import (
    DEFAULT_DAYS,
    DEFAULT_RECIPES,
    audit_production_kit,
    build_production_kit,
    enrich_production_kit_from_raw,
    write_production_kit,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export team-ready, evidence-linked recipe briefs, calendar, "
            "account launch guide and asset verification tasks. Offline."
        )
    )
    parser.add_argument(
        "--workspace", default="data/07_exports/operator-intelligence",
    )
    parser.add_argument("--recipes", type=int, default=DEFAULT_RECIPES)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument(
        "--raw-root", default=None,
        help="Optional local Apify/raw archive with observed captions and sound metadata.",
    )
    parser.add_argument(
        "--clearance-csv", default=None,
        help="Optional team rights-attestation CSV; must name real license evidence.",
    )
    parser.add_argument(
        "--own-results-csv", default=None,
        help="Optional actual first-party post metrics. Never claims operator causation.",
    )
    args = parser.parse_args()

    workspace = _resolve(args.workspace)
    evidence = _load_json(workspace / "evidence.json")
    families = _load_json(workspace / "families.json")
    kit = build_production_kit(
        evidence=evidence,
        families=families,
        accounts=_load_json(workspace / "accounts.json"),
        lab=_load_json(workspace / "lab.json"),
        recipes_limit=args.recipes,
        calendar_days=args.days,
    )
    if args.raw_root:
        enrich_production_kit_from_raw(
            kit, _resolve(args.raw_root), evidence_posts=evidence["posts"]
        )
    audit = audit_production_kit(
        kit,
        post_ids={p["post_uid"] for p in evidence["posts"]},
        family_ids={f["family_id"] for f in families["families"]},
    )
    if audit["status"] != "pass":
        raise SystemExit("Production Kit quality failed:\n" + "\n".join(audit["errors"]))
    result = write_production_kit(kit, workspace=workspace)
    # Private team state is a separate single source of truth and survives
    # future research/rebuild runs. No CSV writes into production.json.
    operating = OperatingStore(workspace)
    try:
        if args.clearance_csv:
            operating.import_asset_attestations(
                _load_csv(_resolve(args.clearance_csv))
            )
        if args.own_results_csv:
            operating.import_first_party_csv(
                _load_csv(_resolve(args.own_results_csv))
            )
        state = operating.view()
    except OperatingError as exc:
        raise SystemExit(f"Operating data import rejected: {exc}") from exc
    print(json.dumps({
        "status": "draft_handoff_ready_for_team_review",
        "output": result["handoff_zip"],
        "recipe_count": len(kit["recipes"]),
        "calendar_posts": len(kit["calendar"]),
        "sound_references_found": len(kit["music_bank"]),
        "team_assets_rights_checked": sum(
            entry.get("state") in ("rights_checked","editorial_checked","ready")
            and not entry.get("needs_recheck")
            for entry in state["asset_work"]
        ),
        "first_party_results_saved": len(state["outcomes"]),
        "private_state_revision": state["revision"],
        "publish_ready": kit["quality"]["ready_to_publish"],
        "source_fingerprint": kit["source_fingerprint"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
