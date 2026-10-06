#!/usr/bin/env python3
"""Export a share-safe JSON bundle from creative_master for dashboard/showcase use."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.showcase_media import export_media_for_post, select_media_keys

SHOWCASE_SCHEMA_VERSION = "creative-showcase-v1"

DIMENSIONS = (
    "content_type",
    "primary_language_code",
    "audience_segment",
    "content_angle",
    "value_type",
    "hook_technique",
    "content_format",
    "video_format",
    "dominant_visual_type",
    "product_family",
    "product_placement_style",
    "cta_type",
)

PUBLIC_POST_FIELDS = (
    "content_type",
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
    "audience_segment",
    "content_angle",
    "value_type",
    "hook_technique",
    "content_format",
    "video_format",
    "dominant_visual_type",
    "product_family",
    "product_placement_style",
    "cta_type",
    "slide_count",
    "duration_seconds",
    "product_position",
    "product_position_unit",
    "cta_position",
    "cta_position_unit",
)

TEXT_FIELDS = (
    "hook_text",
    "topic",
    "pain_point",
    "desired_outcome",
    "creative_formula",
)

IDENTITY_FIELDS = ("account", "post_id", "url")


def _json_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _median(df: pd.DataFrame, column: str) -> float | None:
    series = _numeric(df, column).dropna()
    return None if series.empty else float(series.median())


def _quantile(df: pd.DataFrame, column: str, q: float) -> float | None:
    series = _numeric(df, column).dropna()
    return None if series.empty else float(series.quantile(q))


def _sum(df: pd.DataFrame, column: str) -> int | float | None:
    series = _numeric(df, column).dropna()
    if series.empty:
        return None
    value = float(series.sum())
    return int(value) if value.is_integer() else value


def _rate(mask: pd.Series) -> float | None:
    clean = mask.dropna()
    return None if clean.empty else float(clean.mean())


def _clean_category(value: Any) -> str | None:
    value = _json_scalar(value)
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "<na>"} else None


def _account_aliases(df: pd.DataFrame) -> dict[str, str]:
    accounts = sorted(
        str(x).strip()
        for x in df.get("account", pd.Series(dtype=str)).dropna().unique()
    )
    return {
        account: f"Creator {i:02d}"
        for i, account in enumerate(accounts, start=1)
    }


def _global_p95_threshold(df: pd.DataFrame) -> float | None:
    return _quantile(df, "views", 0.95)


def _top25_mask(df: pd.DataFrame) -> pd.Series:
    values = _numeric(df, "account_views_pct")
    return values.ge(0.75).where(values.notna())


def _global_p95_mask(df: pd.DataFrame, threshold: float | None) -> pd.Series:
    values = _numeric(df, "views")
    if threshold is None:
        return pd.Series(
            [pd.NA] * len(df),
            index=df.index,
            dtype="boolean",
        )
    return values.ge(threshold).where(values.notna())


def build_overview(
    df: pd.DataFrame,
    *,
    include_identities: bool,
    include_text: bool,
    media_mode: str,
) -> dict[str, Any]:
    created = pd.to_datetime(
        df.get("created_at"),
        errors="coerce",
        utc=True,
    )
    content_counts = (
        {
            str(k): int(v)
            for k, v in df["content_type"].value_counts(dropna=False).items()
        }
        if "content_type" in df.columns
        else {}
    )
    views = _numeric(df, "views").dropna()
    return {
        "schema_version": SHOWCASE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "privacy": {
            "identities_included": include_identities,
            "free_text_included": include_text,
            "raw_analysis_included": False,
            "source_media_paths_included": False,
            "media_mode": media_mode,
        },
        "dataset": {
            "posts": int(len(df)),
            "accounts": (
                int(df["account"].nunique())
                if "account" in df.columns
                else 0
            ),
            "date_min": (
                None if created.isna().all() else created.min().isoformat()
            ),
            "date_max": (
                None if created.isna().all() else created.max().isoformat()
            ),
            "content_types": content_counts,
        },
        "performance": {
            "total_views": _sum(df, "views"),
            "median_views": _median(df, "views"),
            "p90_views": _quantile(df, "views", 0.90),
            "p95_views": _quantile(df, "views", 0.95),
            "p99_views": _quantile(df, "views", 0.99),
            "max_views": None if views.empty else float(views.max()),
            "median_save_rate": _median(df, "save_rate"),
            "median_share_rate": _median(df, "share_rate"),
        },
        "notes": [
            (
                "Metrics describe this research dataset only; they are not "
                "universal platform benchmarks."
            ),
            (
                "Top-25% rates use each account's own historical view "
                "percentile when available."
            ),
            (
                "Creative labels are derived interpretations and should be "
                "treated as evidence, not ground truth."
            ),
        ],
    }


def build_accounts(
    df: pd.DataFrame,
    aliases: dict[str, str],
    *,
    include_identities: bool,
) -> list[dict[str, Any]]:
    p95 = _global_p95_threshold(df)
    rows: list[dict[str, Any]] = []
    if "account" not in df.columns:
        return rows

    for account, group in df.groupby("account", dropna=True):
        account_key = str(account).strip()
        row: dict[str, Any] = {
            "account_alias": aliases.get(account_key, "Creator ?"),
            "posts": int(len(group)),
            "total_views": _sum(group, "views"),
            "median_views": _median(group, "views"),
            "p95_views": _quantile(group, "views", 0.95),
            "median_save_rate": _median(group, "save_rate"),
            "median_share_rate": _median(group, "share_rate"),
            "top25_rate": _rate(_top25_mask(group)),
            "global_p95_rate": _rate(_global_p95_mask(group, p95)),
        }
        if "content_type" in group.columns:
            row["content_types"] = {
                str(k): int(v)
                for k, v in group["content_type"].value_counts().items()
            }
        if include_identities:
            row["account"] = account_key
        rows.append(row)

    return sorted(
        rows,
        key=lambda r: (-(r.get("posts") or 0), r["account_alias"]),
    )


def build_timeline(df: pd.DataFrame) -> list[dict[str, Any]]:
    if "created_at" not in df.columns:
        return []

    work = df.copy()
    work["_created_at"] = pd.to_datetime(
        work["created_at"],
        errors="coerce",
        utc=True,
    )
    work = work[work["_created_at"].notna()].copy()
    if work.empty:
        return []

    work["month"] = work["_created_at"].dt.strftime("%Y-%m")
    p95 = _global_p95_threshold(work)
    rows = []

    for month, group in work.groupby("month", sort=True):
        rows.append(
            {
                "month": month,
                "posts": int(len(group)),
                "accounts": (
                    int(group["account"].nunique())
                    if "account" in group.columns
                    else 0
                ),
                "total_views": _sum(group, "views"),
                "median_views": _median(group, "views"),
                "median_save_rate": _median(group, "save_rate"),
                "median_share_rate": _median(group, "share_rate"),
                "global_p95_posts": int(
                    _global_p95_mask(group, p95)
                    .fillna(False)
                    .sum()
                ),
            }
        )

    return rows


def build_dimensions(
    df: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    p95 = _global_p95_threshold(df)
    output: dict[str, list[dict[str, Any]]] = {}

    for dimension in DIMENSIONS:
        if dimension not in df.columns:
            continue

        values = df[dimension].map(_clean_category)
        rows = []

        for value in sorted(
            x for x in values.dropna().unique()
        ):
            group = df[values.eq(value)]
            rows.append(
                {
                    "value": value,
                    "posts": int(len(group)),
                    "accounts": (
                        int(group["account"].nunique())
                        if "account" in group.columns
                        else 0
                    ),
                    "median_views": _median(group, "views"),
                    "median_save_rate": _median(group, "save_rate"),
                    "median_share_rate": _median(group, "share_rate"),
                    "top25_rate": _rate(_top25_mask(group)),
                    "global_p95_rate": _rate(
                        _global_p95_mask(group, p95)
                    ),
                }
            )

        output[dimension] = sorted(
            rows,
            key=lambda r: (-r["posts"], r["value"]),
        )

    return output


def build_posts(
    df: pd.DataFrame,
    aliases: dict[str, str],
    *,
    include_identities: bool,
    include_text: bool,
    out_dir: Path,
    media_mode: str,
    media_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    work = df.copy()
    work["_created_at"] = pd.to_datetime(
        work.get("created_at"),
        errors="coerce",
        utc=True,
    )

    sort_cols = [
        c
        for c in ["_created_at", "account", "post_id"]
        if c in work.columns
    ]
    if sort_cols:
        work = (
            work.sort_values(sort_cols, na_position="last")
            .reset_index(drop=True)
        )

    rows: list[dict[str, Any]] = []

    for i, record in enumerate(
        work.to_dict(orient="records"),
        start=1,
    ):
        account = _clean_category(record.get("account")) or ""
        row: dict[str, Any] = {
            "post_key": f"Post {i:04d}",
            "account_alias": aliases.get(account, "Creator ?"),
        }

        for field in PUBLIC_POST_FIELDS:
            if field in record:
                value = record[field]
                if field == "created_at":
                    value = pd.to_datetime(
                        value,
                        errors="coerce",
                        utc=True,
                    )
                row[field] = _json_scalar(value)

        if include_text:
            for field in TEXT_FIELDS:
                if field in record:
                    row[field] = _json_scalar(record[field])

        if include_identities:
            for field in IDENTITY_FIELDS:
                if field in record:
                    row[field] = _json_scalar(record[field])

        key = (
            str(record.get("account") or ""),
            str(record.get("post_id") or ""),
        )
        if media_mode != "none" and key in media_keys:
            row.update(
                export_media_for_post(
                    record,
                    row["post_key"],
                    out_dir,
                    mode=media_mode,
                )
            )

        rows.append(row)

    return rows


def ai_studio_prompt() -> str:
    return """# AI Studio Build prompt — Creative Evidence Showcase

Build a polished, responsive analytics dashboard from the attached JSON files:
`overview.json`, `accounts.json`, `timeline.json`,
`dimensions.json`, and `posts.json`.

## Hard rules
- Treat the attached JSON files as the only source of numeric truth.
- Never invent, estimate, or silently recalculate missing metrics.
- Preserve anonymized creator labels exactly as provided.
- Clearly label claims as observations from this dataset, not universal TikTok benchmarks.
- Do not expose hidden IDs, raw analysis JSON, source media paths, or anything not present in the files.
- The dashboard itself should render from the JSON data without requiring Gemini calls.
- If a post contains `thumbnail_path`, render it as a lazy-loaded image card.
- If a post contains `video_path`, render an inline muted video preview with controls and poster/thumbnail when available.

## Product goal
Make this feel like a research artifact worth sharing publicly: clean, credible,
visual, data-dense, and easy to screenshot for social posts.

## Pages / sections
1. Overview
   - hero: posts analyzed, creators, date range, slideshow/video split
   - total views, median views, P95/P99 views, median save/share rate
   - short methodology/disclaimer callout

2. Performance explorer
   - account comparison using account aliases
   - monthly posting volume and view trend
   - top-25% and global-P95 rates
   - filters for content type and creator

3. Creative explorer
   - hook technique
   - content angle
   - audience segment
   - visual type
   - language
   - product placement
   - CTA type
   For each dimension show post count, account coverage, median views,
   median save/share rates, top25 rate, and global-P95 rate.

4. Winner vs baseline
   - emphasize account-relative performance, not raw views alone
   - show which categorical values have the strongest top25 rate while
     displaying sample size beside every result
   - never imply causality

5. Post explorer
   - searchable/filterable table using `posts.json`
   - use a visual card/grid mode when `thumbnail_path` exists
   - show inline video preview when `video_path` exists
   - show only fields present in the file
   - if text fields are absent, do not invent them

## Visual direction
- editorial research dashboard, not a generic admin panel
- strong typography, generous whitespace, compact metric cards
- dark/light friendly
- charts should have descriptive titles and tooltips
- always show sample size near comparisons
- use concise annotation such as “Observed in this dataset”
- responsive on desktop and mobile

## Optional AI feature
If adding an “Ask the dataset” feature, place it behind a separate server-side
Gemini route. It may summarize only the attached aggregate/post JSON and must
cite which dimensions/metrics support its answer. The core dashboard must work
fully without it.
"""


def export_showcase(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    include_identities: bool = False,
    include_text: bool = False,
    media_mode: str = "none",
    media_limit: int = 100,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    aliases = _account_aliases(df)
    if media_mode not in {"none", "thumbnails", "previews"}:
        raise ValueError(f"Unsupported media_mode: {media_mode}")

    media_keys = (
        select_media_keys(df.to_dict(orient="records"), limit=media_limit)
        if media_mode != "none"
        else set()
    )

    overview = build_overview(
        df,
        include_identities=include_identities,
        include_text=include_text,
        media_mode=media_mode,
    )
    accounts = build_accounts(
        df,
        aliases,
        include_identities=include_identities,
    )
    timeline = build_timeline(df)
    dimensions = build_dimensions(df)
    posts = build_posts(
        df,
        aliases,
        include_identities=include_identities,
        include_text=include_text,
        out_dir=out_dir,
        media_mode=media_mode,
        media_keys=media_keys,
    )

    _write_json(out_dir / "overview.json", overview)
    _write_json(out_dir / "accounts.json", accounts)
    _write_json(out_dir / "timeline.json", timeline)
    _write_json(out_dir / "dimensions.json", dimensions)
    _write_json(out_dir / "posts.json", posts)

    (out_dir / "AI_STUDIO_PROMPT.md").write_text(
        ai_studio_prompt(),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": SHOWCASE_SCHEMA_VERSION,
        "generated_at": overview["generated_at"],
        "rows": int(len(df)),
        "files": [
            "overview.json",
            "accounts.json",
            "timeline.json",
            "dimensions.json",
            "posts.json",
            "AI_STUDIO_PROMPT.md",
        ],
        "share_safe_defaults": (
            not include_identities and not include_text
        ),
        "identities_included": include_identities,
        "free_text_included": include_text,
        "media_mode": media_mode,
        "media_limit": media_limit if media_mode != "none" else 0,
        "media_posts_selected": len(media_keys),
    }
    _write_json(out_dir / "manifest.json", manifest)
    return manifest


def _read_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing input: {path}")

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)

    raise SystemExit(f"Unsupported table format: {path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Export a share-safe JSON/media bundle from creative_master "
            "for dashboard/showcase use."
        )
    )
    ap.add_argument(
        "master",
        help="creative_master.parquet/csv/jsonl",
    )
    ap.add_argument(
        "--out",
        default="data/06_showcase",
    )
    ap.add_argument(
        "--include-identities",
        action="store_true",
        help=(
            "Include raw account, post_id, and URL. "
            "Off by default for public sharing."
        ),
    )
    ap.add_argument(
        "--include-text",
        action="store_true",
        help=(
            "Include hook/topic/formula free text. "
            "Off by default for public sharing."
        ),
    )
    ap.add_argument(
        "--media",
        choices=["none", "thumbnails", "previews"],
        default="none",
        help=(
            "Optional visual assets. thumbnails copies one cover/first-slide "
            "image per selected post; previews also copies selected video files."
        ),
    )
    ap.add_argument(
        "--media-limit",
        type=int,
        default=100,
        help=(
            "Maximum posts to receive media assets, ranked by global view "
            "percentile/views. Use 0 for all posts."
        ),
    )
    args = ap.parse_args()

    master = Path(args.master).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()

    manifest = export_showcase(
        _read_master(master),
        out,
        include_identities=args.include_identities,
        include_text=args.include_text,
        media_mode=args.media,
        media_limit=args.media_limit,
    )

    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
    )
    print(out)


if __name__ == "__main__":
    main()
