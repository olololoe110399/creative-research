"""Pure normalization and assembly of canonical slideshow/video evidence."""

from __future__ import annotations

from typing import Any

import pandas as pd

from creative_research.constants import MASTER_SCHEMA_VERSION


def _series(df: pd.DataFrame, name: str, default: Any = pd.NA) -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df), index=df.index)


def _canonical_media_path(df: pd.DataFrame, prefix: str) -> pd.Series:
    accounts = _series(df, "account").astype("string").fillna("")
    post_ids = _series(df, "post_id").astype("string").fillna("")
    return pd.Series(
        [
            f"{prefix}/{account}/{post_id}"
            for account, post_id in zip(accounts, post_ids, strict=True)
        ],
        index=df.index,
        dtype="string",
    )


def _base(df: pd.DataFrame, content_type: str) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["master_schema_version"] = MASTER_SCHEMA_VERSION
    out["content_type"] = content_type
    for col in [
        "account",
        "post_id",
        "url",
        "created_at",
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "share_rate",
        "save_rate",
        "account_views_pct",
        "global_views_pct",
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
        "hook_technique",
        "hook_psychological_trigger",
        "hook_replicable_formula",
        "narrative_structure",
        "dominant_visual_type",
        "visual_aesthetic",
        "text_overlay_style",
        "proof_or_credibility",
        "product_family",
        "product_placement_style",
        "product_evidence",
        "cta_type",
        "cta_evidence",
        "creative_formula",
        "attention_mechanisms",
        "overall_confidence",
        "uncertainty_notes",
        "validation_events",
        "analysis_json",
    ]:
        out[col] = _series(df, col)
    return out


def normalize_slides(df: pd.DataFrame) -> pd.DataFrame:
    out = _base(df, "slideshow")
    out["source_media_path"] = _canonical_media_path(df, "data/02_media/tiktok")
    out["slide_count"] = _series(df, "slide_count")
    out["duration_seconds"] = pd.NA

    out["hook_text"] = _series(df, "hook_text")
    out["hook_position"] = _series(df, "hook_slide")
    out["hook_position_end"] = _series(df, "hook_slide")
    out["hook_position_unit"] = "slide"

    out["content_format"] = _series(df, "content_format")
    out["video_format"] = pd.NA
    out["image_realism"] = _series(df, "image_realism")
    out["pinterest_like_aesthetic"] = _series(df, "pinterest_like_aesthetic")
    out["pinterest_note"] = _series(df, "pinterest_note")
    out["visual_consistency"] = _series(df, "visual_consistency")

    out["has_product"] = _series(df, "has_visible_product", False)
    out["product_name"] = _series(df, "visible_product_name")
    out["product_position"] = _series(df, "product_first_slide")
    out["product_position_unit"] = "slide"

    out["has_cta"] = _series(df, "has_visible_cta", False)
    out["cta_text"] = _series(df, "cta_text")
    out["cta_position"] = _series(df, "cta_slide")
    out["cta_position_unit"] = "slide"
    out["cta_modality"] = pd.NA

    for col in [
        "hook_spoken_text",
        "hook_overlay_text",
        "spoken_transcript",
        "editing_style",
        "camera_style",
        "face_or_person_present",
        "has_speech",
        "has_background_music",
        "narration_style",
        "pacing",
        "timeline_json",
        "width",
        "height",
        "fps",
    ]:
        out[col] = pd.NA
    return out


def normalize_videos(df: pd.DataFrame) -> pd.DataFrame:
    out = _base(df, "video")
    out["source_media_path"] = _canonical_media_path(df, "data/03_video_media")
    out["slide_count"] = pd.NA
    out["duration_seconds"] = _series(df, "duration_seconds")

    spoken = _series(df, "hook_spoken_text")
    overlay = _series(df, "hook_overlay_text")
    spoken_text = spoken.astype("string")
    out["hook_text"] = spoken.where(spoken.notna() & spoken_text.str.len().fillna(0).gt(0), overlay)
    out["hook_position"] = _series(df, "hook_start_second")
    out["hook_position_end"] = _series(df, "hook_end_second")
    out["hook_position_unit"] = "second"

    out["content_format"] = pd.NA
    out["video_format"] = _series(df, "video_format")
    out["image_realism"] = pd.NA
    out["pinterest_like_aesthetic"] = pd.NA
    out["pinterest_note"] = pd.NA
    out["visual_consistency"] = pd.NA

    out["has_product"] = _series(df, "has_product", False)
    out["product_name"] = _series(df, "product_name")
    out["product_position"] = _series(df, "product_first_second")
    out["product_position_unit"] = "second"

    out["has_cta"] = _series(df, "has_explicit_cta", False)
    out["cta_text"] = _series(df, "cta_text_or_speech")
    out["cta_position"] = _series(df, "cta_second")
    out["cta_position_unit"] = "second"
    out["cta_modality"] = _series(df, "cta_modality")

    out["hook_spoken_text"] = spoken
    out["hook_overlay_text"] = overlay
    out["spoken_transcript"] = _series(df, "spoken_transcript")
    out["editing_style"] = _series(df, "editing_style")
    out["camera_style"] = _series(df, "camera_style")
    out["face_or_person_present"] = _series(df, "face_or_person_present")
    out["has_speech"] = _series(df, "has_speech")
    out["has_background_music"] = _series(df, "has_background_music")
    out["narration_style"] = _series(df, "narration_style")
    out["pacing"] = _series(df, "pacing")
    out["timeline_json"] = _series(df, "timeline_json")
    out["width"] = _series(df, "width")
    out["height"] = _series(df, "height")
    out["fps"] = _series(df, "fps")
    return out


def build_master(slides_raw: pd.DataFrame, videos_raw: pd.DataFrame) -> pd.DataFrame:
    slides = normalize_slides(slides_raw)
    videos = normalize_videos(videos_raw)
    all_columns = list(dict.fromkeys([*slides.columns, *videos.columns]))
    parts = [slides.dropna(axis=1, how="all"), videos.dropna(axis=1, how="all")]
    master = pd.concat(parts, ignore_index=True, sort=False).reindex(columns=all_columns)

    master["account"] = master["account"].astype("string").str.strip()
    master["post_id"] = master["post_id"].astype("string").str.strip()
    master["created_at"] = pd.to_datetime(master["created_at"], errors="coerce", utc=True)

    dup_mask = master.duplicated(["account", "post_id"], keep=False)
    if dup_mask.any():
        duplicates = master.loc[dup_mask, ["account", "post_id", "content_type"]]
        raise ValueError(
            "Duplicate account+post_id across master inputs:\n" + duplicates.to_string(index=False)
        )

    return master.sort_values(["created_at", "account", "post_id"], na_position="last").reset_index(
        drop=True
    )
