#!/usr/bin/env python3
"""Refresh team handoff from materialized evidence; no scrape or model calls."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from creative_research.pathing import project_root
from creative_research.production_kit import (
    DEFAULT_DAYS,
    DEFAULT_RECIPES,
    apply_team_asset_clearance,
    attach_own_experiment_outcomes,
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
    kit = build_production_kit(
        evidence=evidence,
        families=_load_json(workspace / "families.json"),
        accounts=_load_json(workspace / "accounts.json"),
        lab=_load_json(workspace / "lab.json"),
        recipes_limit=args.recipes,
        calendar_days=args.days,
    )
    if args.raw_root:
        enrich_production_kit_from_raw(
            kit, _resolve(args.raw_root), evidence_posts=evidence["posts"]
        )
    if args.clearance_csv:
        apply_team_asset_clearance(kit, _load_csv(_resolve(args.clearance_csv)))
    if args.own_results_csv:
        attach_own_experiment_outcomes(
            kit, _load_csv(_resolve(args.own_results_csv))
        )
    audit = audit_production_kit(
        kit, post_ids={p["post_uid"] for p in evidence["posts"]}
    )
    if audit["status"] != "pass":
        raise SystemExit("Production Kit quality failed:\n" + "\n".join(audit["errors"]))
    result = write_production_kit(kit, workspace=workspace)
    print(json.dumps({
        "status": "draft_handoff_ready_for_team_review",
        "output": result["handoff_zip"],
        "recipe_count": len(kit["recipes"]),
        "calendar_posts": len(kit["calendar"]),
        "sound_references_found": len(kit["music_bank"]),
        "asset_rights_attested": kit["quality"]["assets_with_verified_rights"],
        "publish_ready": kit["quality"]["ready_to_publish"],
        "source_fingerprint": kit["source_fingerprint"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
