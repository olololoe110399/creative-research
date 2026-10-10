#!/usr/bin/env python3
"""Build the canonical manifest for all locally archived slideshow posts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.infrastructure.paths import portable_path, resolve_path
from creative_research.infrastructure.storage import atomic_output, write_csv
from creative_research.infrastructure.storage import write_text as atomic_write_text

MANIFEST_COLUMNS = [
    "account",
    "post_id",
    "post_dir",
    "url",
    "created_at",
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "slide_count",
]


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def discover_slideshows(root: Path, *, path_base: Path | None = None) -> pd.DataFrame:
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(root)

    rows: list[dict[str, Any]] = []
    for account_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        account = account_dir.name
        for post_dir in sorted(account_dir.iterdir()):
            if not post_dir.is_dir() or post_dir.name == "profile":
                continue

            meta = read_json(post_dir / "meta.json")
            raw = read_json(post_dir / "raw.json")
            if not meta and not raw:
                continue

            slide_files = sorted(post_dir.glob("slide_*.*"))
            explicit = meta.get("is_slideshow")
            if explicit is None:
                explicit = raw.get("isSlideshow")
            is_slideshow = bool(explicit)
            if not is_slideshow or not slide_files:
                continue

            rows.append(
                {
                    "account": account,
                    "post_id": str(
                        meta.get("post_id") or raw.get("id") or raw.get("idStr") or post_dir.name
                    ),
                    "post_dir": portable_path(post_dir, path_base),
                    "url": meta.get("url") or raw.get("webVideoUrl"),
                    "created_at": meta.get("created_at") or raw.get("createTimeISO"),
                    "views": meta.get("views", raw.get("playCount")),
                    "likes": meta.get("likes", raw.get("diggCount")),
                    "comments": meta.get("comments", raw.get("commentCount")),
                    "shares": meta.get("shares", raw.get("shareCount")),
                    "saves": meta.get("saves", raw.get("collectCount")),
                    "slide_count": len(slide_files),
                }
            )

    df = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    for col in ["views", "likes", "comments", "shares", "saves", "slide_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["share_rate"] = df["shares"] / df["views"].replace(0, pd.NA)
    df["save_rate"] = df["saves"] / df["views"].replace(0, pd.NA)
    df["account_views_pct"] = df.groupby("account")["views"].rank(pct=True, method="average")
    df["global_views_pct"] = df["views"].rank(pct=True, method="average")
    return df.sort_values(["created_at", "account", "post_id"]).reset_index(drop=True)


def write_manifest(df: pd.DataFrame, out: Path, input_root: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "full_manifest.csv", df, index=False, encoding="utf-8-sig")

    with atomic_output(out / "full_manifest.jsonl") as temporary:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in df.to_dict(orient="records"):
                if hasattr(row.get("created_at"), "isoformat"):
                    row["created_at"] = row["created_at"].isoformat()
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    report = {
        "input": portable_path(input_root),
        "posts": int(len(df)),
        "accounts": int(df["account"].nunique()),
        "slides": int(df["slide_count"].fillna(0).sum()),
        "account_counts": {
            str(k): int(v) for k, v in df["account"].value_counts().sort_index().to_dict().items()
        },
    }
    atomic_write_text(out / "report.json", json.dumps(report, ensure_ascii=False, indent=2))
    return report


def run(
    *,
    input_dir: str,
    out: str = "data/03_manifests/slides",
) -> None:

    root = resolve_path(input_dir)
    out_path = resolve_path(out)
    try:
        df = discover_slideshows(root)
    except FileNotFoundError:
        raise SystemExit(f"Missing input directory: {root}") from None
    report = write_manifest(df, out_path, root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(out_path / "full_manifest.csv")
