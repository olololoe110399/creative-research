from __future__ import annotations

import json
import math
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from creative_research.pathing import portable_path, project_root, resolve_path
from creative_research.validation import read_table

REFERENCE_EXPORT_SCHEMA_VERSION = "creative-reference-pack-v3"

REFERENCE_FIELDS = [
    "content_type",
    "created_at",
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "save_rate",
    "share_rate",
    "account_views_pct",
    "global_views_pct",
    "primary_language_code",
    "audience_segment",
    "niche",
    "topic",
    "content_angle",
    "value_type",
    "hook_text",
    "hook_position",
    "hook_position_unit",
    "hook_technique",
    "hook_psychological_trigger",
    "hook_replicable_formula",
    "narrative_structure",
    "content_format",
    "video_format",
    "slide_count",
    "duration_seconds",
    "dominant_visual_type",
    "visual_aesthetic",
    "image_realism",
    "text_overlay_style",
    "visual_consistency",
    "pinterest_like_aesthetic",
    "product_family",
    "product_placement_style",
    "has_product",
    "product_name",
    "product_position",
    "product_position_unit",
    "has_cta",
    "cta_type",
    "cta_text",
    "cta_position",
    "cta_position_unit",
    "creative_formula",
    "source_media_path",
]

DEFAULT_GROUP_DIMENSIONS = [
    "hook_technique",
    "content_angle",
    "content_format",
    "product_placement_style",
]

SELECTION_DIVERSITY_DIMENSIONS = (
    "hook_technique",
    "content_angle",
    "content_format",
    "product_placement_style",
    "audience_segment",
    "primary_language_code",
    "dominant_visual_type",
)


def load_master(path: str | Path) -> tuple[Path, pd.DataFrame]:
    resolved = resolve_path(path)
    return resolved, read_table(resolved)


def _numeric(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")
    return pd.to_numeric(df[name], errors="coerce")


def _balanced_score(df: pd.DataFrame) -> pd.Series:
    parts: list[pd.Series] = []
    for name in ("account_views_pct", "global_views_pct"):
        values = _numeric(df, name)
        if values.notna().any():
            parts.append(values.astype(float))
    for name in ("save_rate", "share_rate"):
        values = _numeric(df, name)
        if values.notna().any():
            parts.append(values.rank(pct=True).astype(float))
    if not parts:
        return pd.Series(float("nan"), index=df.index)
    return pd.concat(parts, axis=1).mean(axis=1, skipna=True)


def rank_master(
    df: pd.DataFrame,
    *,
    rank: str = "relative",
    content_type: str = "all",
    top: int | None = None,
) -> pd.DataFrame:
    if content_type != "all":
        if "content_type" not in df.columns:
            raise ValueError("content_type column is required for content filtering")
        work = df.loc[df["content_type"].astype(str) == content_type].copy()
    else:
        work = df.copy()

    if rank == "relative":
        score = _numeric(work, "account_views_pct")
    elif rank == "breakout":
        score = _numeric(work, "global_views_pct")
    elif rank == "saves":
        score = _numeric(work, "save_rate")
    elif rank == "balanced":
        score = _balanced_score(work)
    else:
        raise ValueError(f"Unknown rank mode: {rank}")

    work["rank_score"] = score
    work["_views_sort"] = _numeric(work, "views")
    work = work.sort_values(
        ["rank_score", "_views_sort", "created_at"] if "created_at" in work.columns else ["rank_score", "_views_sort"],
        ascending=False,
        na_position="last",
        kind="mergesort",
    ).drop(columns="_views_sort")
    if top is not None:
        work = work.head(top)
    return work.reset_index(drop=True)


def _account_balanced_select(ranked: pd.DataFrame, top: int) -> pd.DataFrame:
    if ranked.empty:
        return ranked.copy()
    if top <= 0 or top >= len(ranked):
        result = ranked.copy()
        result["selection_reason"] = "account_balanced"
        return result

    work = ranked.copy()
    work["_rank_position"] = range(1, len(work) + 1)
    queues = {
        str(account): group.index.tolist()
        for account, group in work.groupby("account", sort=False, dropna=False)
    }
    accounts = list(queues)
    selected: list[int] = []
    cursor = {account: 0 for account in accounts}
    while len(selected) < top:
        progressed = False
        for account in accounts:
            pos = cursor[account]
            queue = queues[account]
            if pos >= len(queue):
                continue
            selected.append(queue[pos])
            cursor[account] = pos + 1
            progressed = True
            if len(selected) >= top:
                break
        if not progressed:
            break

    result = work.loc[selected].copy()
    result["selection_reason"] = "account_balanced"
    return result.reset_index(drop=True)


def _system_select(ranked: pd.DataFrame, top: int) -> pd.DataFrame:
    if ranked.empty:
        return ranked.copy()
    if top <= 0 or top >= len(ranked):
        result = ranked.copy()
        result["selection_reason"] = "full_population"
        return result

    work = ranked.copy()
    work["_rank_position"] = range(1, len(work) + 1)
    quality = pd.to_numeric(work["rank_score"], errors="coerce")
    work["_selection_quality"] = quality.rank(pct=True).fillna(0.0)

    selected: list[int] = []
    reasons: dict[int, str] = {}
    selected_counts: dict[str, int] = {}
    seen: dict[str, set[str]] = {dimension: set() for dimension in SELECTION_DIVERSITY_DIMENSIONS}

    def add(index: int, reason: str) -> None:
        selected.append(index)
        reasons[index] = reason
        account = str(work.at[index, "account"])
        selected_counts[account] = selected_counts.get(account, 0) + 1
        for dimension in SELECTION_DIVERSITY_DIMENSIONS:
            if dimension not in work.columns:
                continue
            value = work.at[index, dimension]
            if pd.isna(value):
                continue
            text = str(value).strip()
            if text:
                seen[dimension].add(text)

    # First guarantee breadth across accounts when the requested sample allows it.
    best_by_account = (
        work.sort_values("_selection_quality", ascending=False, kind="mergesort")
        .groupby("account", dropna=False, sort=False)
        .head(1)
        .sort_values("_selection_quality", ascending=False, kind="mergesort")
    )
    for index in best_by_account.index:
        if len(selected) >= top:
            break
        add(int(index), "account_coverage")

    remaining = set(work.index) - set(selected)
    account_total = max(1, int(work["account"].nunique()))
    soft_cap = max(2, math.ceil(top / account_total) + 1)

    while len(selected) < top and remaining:
        best_index: int | None = None
        best_score = float("-inf")
        best_novelty = 0.0

        eligible = {
            index
            for index in remaining
            if selected_counts.get(str(work.at[index, "account"]), 0) < soft_cap
        }
        if not eligible:
            eligible = remaining

        for index in eligible:
            row = work.loc[index]
            novelty_parts: list[float] = []
            for dimension in SELECTION_DIVERSITY_DIMENSIONS:
                if dimension not in work.columns:
                    continue
                value = row.get(dimension)
                if pd.isna(value):
                    continue
                text = str(value).strip()
                if text:
                    novelty_parts.append(1.0 if text not in seen[dimension] else 0.0)

            novelty = (
                sum(novelty_parts) / len(novelty_parts)
                if novelty_parts
                else 0.0
            )
            account = str(row.get("account"))
            balance = 1.0 / (1.0 + selected_counts.get(account, 0))
            score = (
                0.45 * float(row["_selection_quality"])
                + 0.35 * novelty
                + 0.20 * balance
            )
            if score > best_score:
                best_score = score
                best_index = int(index)
                best_novelty = novelty

        if best_index is None:
            break
        add(
            best_index,
            "structure_diversity" if best_novelty > 0 else "performance_balance",
        )
        remaining.remove(best_index)

    result = work.loc[selected].copy()
    result["selection_reason"] = [reasons[int(index)] for index in result.index]
    return result.reset_index(drop=True)


def select_reference_candidates(
    df: pd.DataFrame,
    *,
    strategy: str = "system",
    rank: str = "relative",
    content_type: str = "slideshow",
    top: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ranked = rank_master(df, rank=rank, content_type=content_type, top=None)
    ranked["_rank_position"] = range(1, len(ranked) + 1)

    if strategy == "top":
        selected = ranked if top <= 0 else ranked.head(top).copy()
        selected["selection_reason"] = "top_ranked"
    elif strategy == "account-balanced":
        selected = _account_balanced_select(ranked, top)
    elif strategy == "system":
        selected = _system_select(ranked, top)
    else:
        raise ValueError(f"Unknown selection strategy: {strategy}")

    return ranked.reset_index(drop=True), selected.reset_index(drop=True)


def build_reference_rows(
    df: pd.DataFrame,
    *,
    rank_mode: str,
    selection_strategy: str = "top",
) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["reference_schema_version"] = REFERENCE_EXPORT_SCHEMA_VERSION
    out["reference_id"] = [f"REF-{i:04d}" for i in range(1, len(df) + 1)]
    out["rank_position"] = (
        df["_rank_position"]
        if "_rank_position" in df.columns
        else range(1, len(df) + 1)
    )
    out["selection_strategy"] = selection_strategy
    if "selection_reason" in df.columns:
        out["selection_reason"] = df["selection_reason"]
    out["rank_mode"] = rank_mode
    out["rank_score"] = _numeric(df, "rank_score")
    out["source_platform"] = "tiktok"
    out["source_account"] = df["account"] if "account" in df.columns else pd.NA
    out["source_post_id"] = df["post_id"] if "post_id" in df.columns else pd.NA
    out["source_url"] = df["url"] if "url" in df.columns else pd.NA
    for name in REFERENCE_FIELDS:
        if name in df.columns:
            out[name] = df[name]
    out["media_path"] = pd.NA
    return out


def copy_reference_media(
    references: pd.DataFrame,
    out_dir: Path,
    *,
    root: Path | None = None,
) -> pd.DataFrame:
    result = references.copy()
    root = (root or project_root()).resolve()
    media_root = out_dir / "media"
    for idx, row in result.iterrows():
        source_value = row.get("source_media_path")
        if pd.isna(source_value) or not str(source_value).strip():
            continue
        source = Path(str(source_value)).expanduser()
        if not source.is_absolute():
            source = (root / source).resolve()
        if not source.is_dir():
            continue
        ref_id = str(row["reference_id"])
        dest = media_root / ref_id
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, dest)
        result.at[idx, "media_path"] = f"media/{ref_id}"
    return result


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    elif suffix == ".jsonl":
        df.to_json(path, orient="records", lines=True, force_ascii=False, date_format="iso")
    else:
        raise ValueError(f"Unsupported output format: {path}")


def write_reference_pack(
    references: pd.DataFrame,
    *,
    source_master: Path,
    out_dir: Path,
    rank_mode: str,
    content_type: str,
    media_mode: str,
    selection_strategy: str = "top",
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_table(references, out_dir / "references.parquet")
    write_table(references, out_dir / "references.csv")
    write_table(references, out_dir / "references.jsonl")

    manifest = {
        "reference_schema_version": REFERENCE_EXPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_master": portable_path(source_master),
        "rows": int(len(references)),
        "rank_mode": rank_mode,
        "selection_strategy": selection_strategy,
        "content_type": content_type,
        "media_mode": media_mode,
        "columns": list(references.columns),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Creative Reference Pack",
        "",
        f"- Schema: {REFERENCE_EXPORT_SCHEMA_VERSION}",
        f"- References: {len(references)}",
        f"- Rank mode: {rank_mode}",
        f"- Selection strategy: {selection_strategy}",
        f"- Content type: {content_type}",
        f"- Media mode: {media_mode}",
        "",
        "This pack is descriptive source material for downstream creative work.",
        "It does not assert causality or validated creative-family membership.",
        "",
        "## Top references",
        "",
    ]
    for _, row in references.head(20).iterrows():
        hook = str(row.get("hook_text") or "").strip()
        account = str(row.get("source_account") or "")
        score = row.get("rank_score")
        score_text = "n/a" if pd.isna(score) else f"{float(score):.3f}"
        lines.append(f"- {row['reference_id']} · {account} · score {score_text} · {hook[:120]}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


_CONDITION = re.compile(r"^\s*([^<>=!]+?)\s*(>=|<=|!=|=|>|<)\s*(.*?)\s*$")


def _coerce_value(series: pd.Series, raw: str) -> object:
    lowered = raw.lower()
    if lowered in {"null", "none", "na"}:
        return None
    if pd.api.types.is_numeric_dtype(series):
        return float(raw)
    if pd.api.types.is_bool_dtype(series):
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return raw


def apply_conditions(df: pd.DataFrame, conditions: Iterable[str]) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for expression in conditions:
        match = _CONDITION.match(expression)
        if not match:
            raise ValueError(f"Invalid condition: {expression}")
        column, operator, raw = match.groups()
        column = column.strip()
        if column not in df.columns:
            raise ValueError(f"Unknown column in condition: {column}")
        series = df[column]
        value = _coerce_value(series, raw)
        if value is None:
            current = series.isna() if operator == "=" else series.notna()
        elif pd.api.types.is_numeric_dtype(series):
            left = pd.to_numeric(series, errors="coerce")
            right = float(value)
            current = {
                "=": left == right,
                "!=": left != right,
                ">": left > right,
                ">=": left >= right,
                "<": left < right,
                "<=": left <= right,
            }[operator]
        else:
            left = series.astype("string")
            right = str(value)
            current = {
                "=": left == right,
                "!=": left != right,
                ">": left > right,
                ">=": left >= right,
                "<": left < right,
                "<=": left <= right,
            }[operator]
        mask &= current.fillna(False)
    return df.loc[mask].copy()


def group_references(
    df: pd.DataFrame,
    *,
    dimensions: list[str] | None = None,
) -> pd.DataFrame:
    dimensions = dimensions or DEFAULT_GROUP_DIMENSIONS
    missing = [name for name in dimensions if name not in df.columns]
    if missing:
        raise ValueError("Missing grouping columns: " + ", ".join(missing))

    work = df.copy()
    for name in dimensions:
        work[name] = work[name].astype("string").fillna("<missing>")

    account_col = "source_account" if "source_account" in work.columns else "account"
    views_pct = _numeric(work, "account_views_pct")
    global_pct = _numeric(work, "global_views_pct")
    work["_top25"] = views_pct >= 0.75
    work["_global_p95"] = global_pct >= 0.95
    work["_views"] = _numeric(work, "views")
    work["_save_rate"] = _numeric(work, "save_rate")
    work["_share_rate"] = _numeric(work, "share_rate")

    rows: list[dict[str, object]] = []
    for keys, group in work.groupby(dimensions, dropna=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row: dict[str, object] = dict(zip(dimensions, keys))
        row.update(
            {
                "posts": int(len(group)),
                "accounts": int(group[account_col].nunique()) if account_col in group else 0,
                "top25_rate": float(group["_top25"].mean()),
                "global_p95_rate": float(group["_global_p95"].mean()),
                "median_views": float(group["_views"].median()) if group["_views"].notna().any() else pd.NA,
                "median_save_rate": float(group["_save_rate"].median()) if group["_save_rate"].notna().any() else pd.NA,
                "median_share_rate": float(group["_share_rate"].median()) if group["_share_rate"].notna().any() else pd.NA,
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.sort_values(
        ["posts", "top25_rate", "median_views"],
        ascending=False,
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)
    result.insert(0, "group_id", [f"GRP-{i:04d}" for i in range(1, len(result) + 1)])
    return result
