#!/usr/bin/env python3
"""Backfill operator-aware warehouse tables from an existing creative_master.

This stage is deliberately offline:
- it does not scrape TikTok;
- it does not call Gemini;
- it preserves creative_master as the compatibility interface;
- it normalizes existing Vision analysis into reusable canonical tables.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.constants import DEFAULT_MASTER_PATH, WAREHOUSE_SCHEMA_VERSION
from creative_research.identity import normalize_account, stable_account_id, stable_post_id
from creative_research.operator_registry import OperatorRegistry, load_operator_registry
from creative_research.validation import read_table, validate_master

POST_COLUMNS = [
    "url",
    "created_at",
    "content_type",
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "share_rate",
    "save_rate",
    "account_views_pct",
    "global_views_pct",
    "source_media_path",
    "slide_count",
    "duration_seconds",
]

ANALYSIS_COLUMNS = [
    "primary_language_code",
    "secondary_language_codes",
    "mixed_language",
    "audience_segment",
    "niche",
    "topic",
    "content_angle",
    "value_type",
    "pain_point",
    "desired_outcome",
    "hook_text",
    "hook_position",
    "hook_position_end",
    "hook_position_unit",
    "hook_technique",
    "hook_psychological_trigger",
    "hook_replicable_formula",
    "content_format",
    "video_format",
    "narrative_structure",
    "dominant_visual_type",
    "visual_aesthetic",
    "text_overlay_style",
    "editing_style",
    "camera_style",
    "face_or_person_present",
    "has_speech",
    "has_background_music",
    "narration_style",
    "pacing",
    "proof_or_credibility",
    "has_product",
    "product_family",
    "product_name",
    "product_position",
    "product_position_unit",
    "product_placement_style",
    "product_evidence",
    "has_cta",
    "cta_type",
    "cta_text",
    "cta_position",
    "cta_position_unit",
    "cta_modality",
    "cta_evidence",
    "creative_formula",
    "attention_mechanisms",
    "overall_confidence",
    "uncertainty_notes",
    "validation_events",
]


def _clean(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _mapping(
    master: pd.DataFrame,
    registry: OperatorRegistry,
    *,
    allow_unmapped: bool,
) -> tuple[dict[str, tuple[Any, Any]], list[str]]:
    account_map = registry.account_map()
    observed = sorted(
        {
            normalize_account(value)
            for value in master["account"].dropna().astype(str)
            if normalize_account(value)
        }
    )
    unmapped = [account for account in observed if account not in account_map]
    if unmapped and not allow_unmapped:
        handles = ", ".join(f"@{item}" for item in unmapped)
        raise ValueError(
            "Every observed account must belong to a verified operator registry entry. "
            f"Unmapped accounts: {handles}"
        )
    return account_map, unmapped


def _identity_for_row(
    row: dict[str, Any],
    account_map: dict[str, tuple[Any, Any]],
) -> dict[str, Any]:
    account = str(row.get("account") or "").strip()
    post_id = str(row.get("post_id") or "").strip()
    registration = account_map.get(normalize_account(account))
    operator_id = registration[0].operator_id if registration else None
    account_id = registration[1].account_id if registration else stable_account_id(account)
    platform = registration[1].platform if registration else "tiktok"
    return {
        "warehouse_schema_version": WAREHOUSE_SCHEMA_VERSION,
        "post_uid": stable_post_id(account, post_id),
        "operator_id": operator_id,
        "account_id": account_id,
        "platform": platform,
        "account": account,
        "post_id": post_id,
    }


def _build_posts(
    master: pd.DataFrame,
    account_map: dict[str, tuple[Any, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in master.to_dict(orient="records"):
        output = _identity_for_row(record, account_map)
        for column in POST_COLUMNS:
            output[column] = _clean(record.get(column))
        rows.append(output)
    result = pd.DataFrame(rows)
    if not result.empty:
        result["created_at"] = pd.to_datetime(result["created_at"], errors="coerce", utc=True)
        result = result.sort_values(
            ["created_at", "account", "post_id"], na_position="last"
        ).reset_index(drop=True)
    return result


def _build_analysis(
    master: pd.DataFrame,
    account_map: dict[str, tuple[Any, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in master.to_dict(orient="records"):
        output = _identity_for_row(record, account_map)
        output["content_type"] = _clean(record.get("content_type"))
        output["analysis_source"] = "creative_master.analysis_json"
        for column in ANALYSIS_COLUMNS:
            output[column] = _clean(record.get(column))
        output["analysis_json"] = _clean(record.get("analysis_json"))
        rows.append(output)
    return pd.DataFrame(rows)


def _slide_sequence(
    identity: dict[str, Any],
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    slides = analysis.get("slides")
    if not isinstance(slides, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(slides, start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                **identity,
                "content_type": "slideshow",
                "sequence_type": "slide",
                "position": _clean(item.get("slide_index")) or index,
                "start_second": None,
                "end_second": None,
                "role": _clean(item.get("role")),
                "primary_text": _clean(item.get("primary_overlay_text")),
                "spoken_summary": None,
                "overlay_text": _clean(item.get("primary_overlay_text")),
                "visual_type": _clean(item.get("visual_type")),
                "visual_description": _clean(item.get("visual_description")),
                "product_visible": bool(item.get("product_visible", False)),
                "product_family_visible": _clean(item.get("product_family_visible")),
                "confidence": _clean(item.get("confidence")),
                "text_regions_json": _json_text(item.get("text_regions") or []),
                "raw_element_json": _json_text(item),
            }
        )
    return rows


def _video_sequence(
    identity: dict[str, Any],
    record: dict[str, Any],
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    timeline = analysis.get("timeline")
    if not isinstance(timeline, list):
        raw_timeline = record.get("timeline_json")
        if isinstance(raw_timeline, str) and raw_timeline.strip():
            try:
                timeline = json.loads(raw_timeline)
            except json.JSONDecodeError:
                timeline = []
    if not isinstance(timeline, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(timeline, start=1):
        if not isinstance(item, dict):
            continue
        overlay = _clean(item.get("overlay_text"))
        spoken = _clean(item.get("spoken_summary"))
        rows.append(
            {
                **identity,
                "content_type": "video",
                "sequence_type": "timeline_beat",
                "position": index,
                "start_second": _clean(item.get("start_second")),
                "end_second": _clean(item.get("end_second")),
                "role": _clean(item.get("role")),
                "primary_text": overlay or spoken,
                "spoken_summary": spoken,
                "overlay_text": overlay,
                "visual_type": _clean(item.get("visual_type")),
                "visual_description": _clean(item.get("visual_description")),
                "product_visible": bool(item.get("product_visible", False)),
                "product_family_visible": _clean(item.get("product_family_visible")),
                "confidence": None,
                "text_regions_json": None,
                "raw_element_json": _json_text(item),
            }
        )
    return rows


def _build_sequence(
    master: pd.DataFrame,
    account_map: dict[str, tuple[Any, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in master.to_dict(orient="records"):
        identity = _identity_for_row(record, account_map)
        analysis = _parse_json(record.get("analysis_json"))
        if record.get("content_type") == "slideshow":
            rows.extend(_slide_sequence(identity, analysis))
        elif record.get("content_type") == "video":
            rows.extend(_video_sequence(identity, record, analysis))
    return pd.DataFrame(rows)


def _build_accounts(
    master: pd.DataFrame,
    account_map: dict[str, tuple[Any, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    counts = master.groupby("account", dropna=False).size().to_dict()
    for account in sorted(master["account"].dropna().astype(str).unique()):
        registration = account_map.get(normalize_account(account))
        operator = registration[0] if registration else None
        account_reg = registration[1] if registration else None
        rows.append(
            {
                "warehouse_schema_version": WAREHOUSE_SCHEMA_VERSION,
                "account_id": (
                    account_reg.account_id if account_reg else stable_account_id(account)
                ),
                "operator_id": operator.operator_id if operator else None,
                "platform": account_reg.platform if account_reg else "tiktok",
                "account": account,
                "configured_role": account_reg.role if account_reg else None,
                "verified_operator": bool(operator.verified) if operator else False,
                "verification_method": operator.verification_method if operator else None,
                "observed_posts": int(counts.get(account, 0)),
            }
        )
    return pd.DataFrame(rows)


def _build_operators(
    accounts: pd.DataFrame,
    registry: OperatorRegistry,
) -> pd.DataFrame:
    account_counts = accounts.groupby("operator_id", dropna=False)["account_id"].nunique()
    post_counts = accounts.groupby("operator_id", dropna=False)["observed_posts"].sum()
    rows: list[dict[str, Any]] = []
    for operator in registry.operators:
        rows.append(
            {
                "warehouse_schema_version": WAREHOUSE_SCHEMA_VERSION,
                "operator_id": operator.operator_id,
                "name": operator.name,
                "verified": operator.verified,
                "verification_method": operator.verification_method,
                "verified_at": operator.verified_at,
                "notes": operator.notes,
                "configured_accounts": len(operator.accounts),
                "observed_accounts": int(account_counts.get(operator.operator_id, 0)),
                "observed_posts": int(post_counts.get(operator.operator_id, 0)),
            }
        )
    return pd.DataFrame(rows)


def build_warehouse(
    master: pd.DataFrame,
    registry: OperatorRegistry,
    *,
    allow_unmapped: bool = False,
) -> dict[str, pd.DataFrame]:
    validation = validate_master(master)
    if not validation.ok:
        errors = "; ".join(f"{issue.code}: {issue.message}" for issue in validation.issues)
        raise ValueError(f"creative_master is invalid: {errors}")

    account_map, _ = _mapping(master, registry, allow_unmapped=allow_unmapped)
    accounts = _build_accounts(master, account_map)
    return {
        "operators": _build_operators(accounts, registry),
        "accounts": accounts,
        "posts": _build_posts(master, account_map),
        "creative_analysis": _build_analysis(master, account_map),
        "creative_sequence": _build_sequence(master, account_map),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill operator-aware canonical warehouse tables from an existing "
            "creative_master without scraping or rerunning Vision."
        )
    )
    parser.add_argument(
        "master",
        nargs="?",
        default=str(DEFAULT_MASTER_PATH),
        help="creative_master parquet/csv/jsonl",
    )
    parser.add_argument(
        "--operators",
        required=True,
        help="Verified operator registry TOML (for example config/operators.toml)",
    )
    parser.add_argument("--out", default="data/05_master")
    parser.add_argument(
        "--allow-unmapped",
        action="store_true",
        help="Keep unregistered accounts with operator_id=null instead of failing.",
    )
    args = parser.parse_args()

    master_path = Path(args.master).expanduser().resolve()
    registry_path = Path(args.operators).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    master = read_table(master_path)
    registry = load_operator_registry(registry_path)
    tables = build_warehouse(master, registry, allow_unmapped=args.allow_unmapped)

    outputs: dict[str, str] = {}
    for name, frame in tables.items():
        path = out_dir / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        outputs[name] = str(path)

    post_uids = tables["posts"]["post_uid"]
    if post_uids.duplicated().any():
        raise SystemExit("Warehouse post_uid collision detected")

    report = {
        "warehouse_schema_version": WAREHOUSE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "master": str(master_path),
        "operator_registry": str(registry_path),
        "operators": int(len(tables["operators"])),
        "accounts": int(len(tables["accounts"])),
        "posts": int(len(tables["posts"])),
        "creative_analysis_rows": int(len(tables["creative_analysis"])),
        "creative_sequence_rows": int(len(tables["creative_sequence"])),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No Vision/LLM call was performed.",
            "creative_master remains unchanged and supported.",
        ],
    }
    (out_dir / "warehouse_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
