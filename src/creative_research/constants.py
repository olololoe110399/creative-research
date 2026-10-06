from __future__ import annotations

from pathlib import Path

MASTER_SCHEMA_VERSION = "creative-master-v1"

WORKSPACE_DIRS = (
    "data/00_raw/apify",
    "data/01_selected/targets",
    "data/02_media/tiktok",
    "data/03_manifests/slides",
    "data/03_video_media",
    "data/04_vision/slides",
    "data/04_vision/videos",
    "data/05_master",
    "data/07_exports",
)

DEFAULT_MASTER_PATH = Path("data/05_master/creative_master.parquet")

MASTER_REQUIRED_COLUMNS = {
    "master_schema_version",
    "content_type",
    "account",
    "post_id",
    "created_at",
    "views",
    "shares",
    "saves",
    "source_media_path",
    "primary_language_code",
    "audience_segment",
    "content_angle",
    "hook_technique",
    "product_family",
    "cta_type",
    "creative_formula",
}

ALLOWED_CONTENT_TYPES = {"slideshow", "video"}
