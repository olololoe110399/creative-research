from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.reference_pack import group_references
from creative_research.showcase_media import export_media_for_post

STATIC_FILES = ("index.html", "app.js", "style.css", "favicon.svg")
REQUIRED_DATA_FILES = ("workspace.json", "candidate_groups.json", "manifest.json")


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


def _local_media(out_dir: Path, ref_id: str) -> dict[str, Any]:
    root = out_dir / "media" / ref_id
    if not root.is_dir():
        return {}

    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    video_exts = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
    slides = sorted(
        p for p in root.glob("slide_*.*")
        if p.is_file() and p.suffix.lower() in image_exts
    )
    covers = sorted(
        p for p in root.glob("cover.*")
        if p.is_file() and p.suffix.lower() in image_exts
    )
    videos = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in video_exts
    )
    result: dict[str, Any] = {}
    if covers:
        result["cover_path"] = covers[0].relative_to(out_dir).as_posix()
    elif slides:
        result["cover_path"] = slides[0].relative_to(out_dir).as_posix()
    if slides:
        result["slide_paths"] = [p.relative_to(out_dir).as_posix() for p in slides]
    if videos:
        result["video_path"] = max(videos, key=lambda p: p.stat().st_size).relative_to(out_dir).as_posix()
    return result


def _sequence(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    slides = analysis.get("slides")
    if not isinstance(slides, list):
        return []
    output: list[dict[str, Any]] = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        regions = item.get("text_regions")
        if not isinstance(regions, list):
            regions = []
        output.append(
            {
                "position": _clean(item.get("slide_index")),
                "role": _clean(item.get("role")),
                "primary_text": _clean(item.get("primary_overlay_text")),
                "text_regions": [
                    {
                        "text": _clean(region.get("text")),
                        "kind": _clean(region.get("kind")),
                        "language_code": _clean(region.get("language_code")),
                    }
                    for region in regions
                    if isinstance(region, dict)
                ],
                "visual_type": _clean(item.get("visual_type")),
                "visual_description": _clean(item.get("visual_description")),
                "product_visible": bool(item.get("product_visible", False)),
                "product_family_visible": _clean(item.get("product_family_visible")),
                "confidence": _clean(item.get("confidence")),
            }
        )
    return sorted(output, key=lambda item: item.get("position") or 0)


def _blueprint(reference: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    hook = analysis.get("hook") if isinstance(analysis.get("hook"), dict) else {}
    product = analysis.get("product") if isinstance(analysis.get("product"), dict) else {}
    cta = analysis.get("cta") if isinstance(analysis.get("cta"), dict) else {}
    visual = analysis.get("visual_style") if isinstance(analysis.get("visual_style"), dict) else {}
    sequence = _sequence(analysis)
    return {
        "hook_mechanism": _clean(hook.get("technique") or reference.get("hook_technique")),
        "hook_position": _clean(hook.get("slide_index") or reference.get("hook_position")),
        "sequence_roles": [item.get("role") for item in sequence if item.get("role")],
        "content_format": _clean(analysis.get("content_format") or reference.get("content_format")),
        "narrative_structure": _clean(analysis.get("narrative_structure") or reference.get("narrative_structure")),
        "product_placement_style": _clean(product.get("placement_style") or reference.get("product_placement_style")),
        "product_first_position": _clean(product.get("first_appearance_slide") or reference.get("product_position")),
        "cta_type": _clean(cta.get("cta_type") or reference.get("cta_type")),
        "cta_position": _clean(cta.get("slide_index") or reference.get("cta_position")),
        "dominant_visual_type": _clean(visual.get("dominant_visual_type") or reference.get("dominant_visual_type")),
        "visual_aesthetic": _clean(visual.get("aesthetic") or reference.get("visual_aesthetic")),
        "text_overlay_style": _clean(visual.get("text_overlay_style")),
        "slide_count": _clean(reference.get("slide_count")),
        "creative_formula": _clean(analysis.get("creative_formula") or reference.get("creative_formula")),
    }


def build_reference_detail(
    reference: dict[str, Any],
    source_record: dict[str, Any],
    *,
    out_dir: Path,
    media_mode: str,
) -> dict[str, Any]:
    analysis = _parse_json(source_record.get("analysis_json"))
    hook = analysis.get("hook") if isinstance(analysis.get("hook"), dict) else {}
    product = analysis.get("product") if isinstance(analysis.get("product"), dict) else {}
    cta = analysis.get("cta") if isinstance(analysis.get("cta"), dict) else {}
    visual = analysis.get("visual_style") if isinstance(analysis.get("visual_style"), dict) else {}

    media: dict[str, Any] = {}
    if media_mode in {"remote", "hybrid"}:
        media.update(
            export_media_for_post(
                source_record,
                str(reference["reference_id"]),
                out_dir,
                mode="remote",
            )
        )
    if media_mode in {"copy", "hybrid"}:
        media.update(_local_media(out_dir, str(reference["reference_id"])))

    return {
        "reference_schema_version": reference.get("reference_schema_version"),
        "reference_id": reference.get("reference_id"),
        "source": {
            "platform": reference.get("source_platform"),
            "account": reference.get("source_account"),
            "post_id": reference.get("source_post_id"),
            "url": reference.get("source_url"),
            "created_at": _clean(reference.get("created_at")),
        },
        "selection": {
            "strategy": reference.get("selection_strategy", "top"),
            "rank_mode": reference.get("rank_mode"),
            "rank_position": _clean(reference.get("rank_position")),
            "rank_score": _clean(reference.get("rank_score")),
        },
        "performance": {
            key: _clean(reference.get(key))
            for key in (
                "views", "likes", "comments", "shares", "saves",
                "save_rate", "share_rate", "account_views_pct", "global_views_pct",
            )
        },
        "creative": {
            "language": _clean(reference.get("primary_language_code")),
            "audience": _clean(reference.get("audience_segment")),
            "niche": _clean(reference.get("niche")),
            "topic": _clean(reference.get("topic")),
            "angle": _clean(reference.get("content_angle")),
            "value_type": _clean(reference.get("value_type")),
            "content_format": _clean(reference.get("content_format")),
            "slide_count": _clean(reference.get("slide_count")),
            "hook": {
                "text": _clean(hook.get("text") or reference.get("hook_text")),
                "position": _clean(hook.get("slide_index") or reference.get("hook_position")),
                "technique": _clean(hook.get("technique") or reference.get("hook_technique")),
                "psychological_trigger": _clean(hook.get("psychological_trigger") or reference.get("hook_psychological_trigger")),
                "replicable_formula": _clean(hook.get("replicable_formula") or reference.get("hook_replicable_formula")),
            },
        },
        "sequence": _sequence(analysis),
        "product": {
            "visible": bool(product.get("has_visible_product", reference.get("has_product", False))),
            "name": _clean(product.get("visible_product_name") or reference.get("product_name")),
            "family": _clean(product.get("product_family") or reference.get("product_family")),
            "placement_style": _clean(product.get("placement_style") or reference.get("product_placement_style")),
            "first_position": _clean(product.get("first_appearance_slide") or reference.get("product_position")),
            "evidence": product.get("evidence") if isinstance(product.get("evidence"), list) else [],
        },
        "cta": {
            "visible": bool(cta.get("has_visible_cta", reference.get("has_cta", False))),
            "type": _clean(cta.get("cta_type") or reference.get("cta_type")),
            "text": _clean(cta.get("text") or reference.get("cta_text")),
            "position": _clean(cta.get("slide_index") or reference.get("cta_position")),
            "evidence": cta.get("evidence") if isinstance(cta.get("evidence"), list) else [],
        },
        "visual": {
            "dominant_type": _clean(visual.get("dominant_visual_type") or reference.get("dominant_visual_type")),
            "aesthetic": _clean(visual.get("aesthetic") or reference.get("visual_aesthetic")),
            "image_realism": _clean(visual.get("image_realism")),
            "pinterest_like": _clean(visual.get("pinterest_like_aesthetic") or reference.get("pinterest_like_aesthetic")),
            "text_overlay_style": _clean(visual.get("text_overlay_style")),
            "consistency": _clean(visual.get("visual_consistency_across_slides")),
        },
        "proof_or_credibility": analysis.get("proof_or_credibility") if isinstance(analysis.get("proof_or_credibility"), list) else [],
        "attention_mechanisms": analysis.get("attention_mechanisms_used") if isinstance(analysis.get("attention_mechanisms_used"), list) else [],
        "overall_confidence": _clean(analysis.get("overall_confidence")),
        "uncertainty_notes": analysis.get("uncertainty_notes") if isinstance(analysis.get("uncertainty_notes"), list) else [],
        "blueprint": _blueprint(reference, analysis),
        "media": media,
    }


def sync_reference_workspace(out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    static_root = resources.files("creative_research").joinpath("reference_workspace_static")
    written: list[str] = []
    for name in STATIC_FILES:
        target = out_dir / name
        target.write_bytes(static_root.joinpath(name).read_bytes())
        written.append(name)
    return written


def validate_reference_workspace(root: Path) -> list[str]:
    required = (*STATIC_FILES, *REQUIRED_DATA_FILES)
    return [name for name in required if not (root / name).is_file()]


def write_reference_workspace(
    references: pd.DataFrame,
    source_rows: pd.DataFrame,
    *,
    out_dir: Path,
    media_mode: str,
) -> dict[str, Any]:
    if len(references) != len(source_rows):
        raise ValueError("Reference rows and source rows must have identical length/order")

    details_dir = out_dir / "details"
    details_dir.mkdir(parents=True, exist_ok=True)
    details: list[dict[str, Any]] = []
    for reference, source in zip(
        references.to_dict(orient="records"),
        source_rows.to_dict(orient="records"),
        strict=True,
    ):
        detail = build_reference_detail(reference, source, out_dir=out_dir, media_mode=media_mode)
        details.append(detail)
        (details_dir / f"{detail['reference_id']}.json").write_text(
            json.dumps(detail, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    groups = group_references(references)
    group_rows = groups.where(pd.notna(groups), None).to_dict(orient="records")
    (out_dir / "candidate_groups.json").write_text(
        json.dumps(group_rows, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    payload = {
        "reference_schema_version": references["reference_schema_version"].iloc[0] if len(references) else None,
        "references": details,
    }
    (out_dir / "workspace.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    static_files = sync_reference_workspace(out_dir)
    return {"details": len(details), "groups": len(group_rows), "static_files": static_files}
