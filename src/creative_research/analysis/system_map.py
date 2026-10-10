from __future__ import annotations

from typing import Any

import pandas as pd

SYSTEM_DIMENSIONS = (
    "hook_technique",
    "content_angle",
    "content_format",
    "audience_segment",
    "primary_language_code",
    "product_placement_style",
    "cta_type",
    "dominant_visual_type",
)


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")
    return pd.to_numeric(df[column], errors="coerce")


def _clean(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "<na>"} else None


def _median(df: pd.DataFrame, column: str) -> float | None:
    values = _numeric(df, column).dropna()
    return None if values.empty else float(values.median())


def _quantile(df: pd.DataFrame, column: str, q: float) -> float | None:
    values = _numeric(df, column).dropna()
    return None if values.empty else float(values.quantile(q))


def _rate(mask: pd.Series) -> float | None:
    clean = mask.dropna()
    return None if clean.empty else float(clean.mean())


def _top25_mask(df: pd.DataFrame) -> pd.Series:
    values = _numeric(df, "account_views_pct")
    return values.ge(0.75).where(values.notna())


def _global_p95_mask(df: pd.DataFrame) -> pd.Series:
    values = _numeric(df, "global_views_pct")
    return values.ge(0.95).where(values.notna())


def _content_counts(df: pd.DataFrame) -> dict[str, int]:
    if "content_type" not in df.columns:
        return {}
    return {
        str(key): int(value) for key, value in df["content_type"].value_counts(dropna=False).items()
    }


def _dimension_summary(df: pd.DataFrame, dimension: str) -> list[dict[str, Any]]:
    if dimension not in df.columns:
        return []
    clean = df[dimension].map(_clean)
    rows: list[dict[str, Any]] = []
    for value in sorted(x for x in clean.dropna().unique()):
        group = df.loc[clean.eq(value)]
        rows.append(
            {
                "value": value,
                "posts": int(len(group)),
                "accounts": int(group["account"].nunique()) if "account" in group.columns else 0,
                "share": float(len(group) / len(df)) if len(df) else 0.0,
                "top25_rate": _rate(_top25_mask(group)),
                "global_p95_rate": _rate(_global_p95_mask(group)),
                "median_views": _median(group, "views"),
                "median_save_rate": _median(group, "save_rate"),
                "median_share_rate": _median(group, "share_rate"),
            }
        )
    return sorted(rows, key=lambda row: (-row["posts"], str(row["value"])))


def _account_cadence(group: pd.DataFrame) -> dict[str, Any]:
    created = pd.to_datetime(group.get("created_at"), errors="coerce", utc=True)
    valid = created.dropna()
    if valid.empty:
        return {
            "active_days": 0,
            "median_posts_per_active_day": None,
            "max_posts_per_day": None,
            "first_post": None,
            "last_post": None,
        }
    per_day = valid.dt.strftime("%Y-%m-%d").value_counts()
    return {
        "active_days": int(len(per_day)),
        "median_posts_per_active_day": float(per_day.median()),
        "max_posts_per_day": int(per_day.max()),
        "first_post": valid.min().isoformat(),
        "last_post": valid.max().isoformat(),
    }


def _account_rows(
    master: pd.DataFrame,
    population: pd.DataFrame,
    references: pd.DataFrame,
) -> list[dict[str, Any]]:
    if "account" not in master.columns:
        return []
    selected_counts = (
        references["source_account"].astype("string").value_counts().to_dict()
        if "source_account" in references.columns
        else {}
    )
    population_counts = (
        population["account"].astype("string").value_counts().to_dict()
        if "account" in population.columns
        else {}
    )
    rows: list[dict[str, Any]] = []
    for account, group in master.groupby("account", dropna=True):
        account_key = str(account)
        row = {
            "account": account_key,
            "posts": int(len(group)),
            "population_posts": int(population_counts.get(account_key, 0)),
            "selected_references": int(selected_counts.get(account_key, 0)),
            "content_types": _content_counts(group),
            "median_views": _median(group, "views"),
            "top25_rate": _rate(_top25_mask(group)),
            "global_p95_rate": _rate(_global_p95_mask(group)),
            "median_save_rate": _median(group, "save_rate"),
            "median_share_rate": _median(group, "share_rate"),
            **_account_cadence(group),
        }
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["posts"], row["account"]))


def _dimension_coverage(
    population: pd.DataFrame,
    references: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for dimension in SYSTEM_DIMENSIONS:
        if dimension not in population.columns or dimension not in references.columns:
            continue
        source_values = set(population[dimension].map(_clean).dropna().tolist())
        selected_values = set(references[dimension].map(_clean).dropna().tolist())
        result[dimension] = {
            "population_values": len(source_values),
            "selected_values": len(selected_values),
            "coverage": (
                float(len(selected_values) / len(source_values)) if source_values else None
            ),
            "missing_values": sorted(source_values - selected_values),
        }
    return result


def build_system_map(
    master: pd.DataFrame,
    population: pd.DataFrame,
    references: pd.DataFrame,
    *,
    strategy: str,
    content_type: str,
) -> dict[str, Any]:
    created = pd.to_datetime(master.get("created_at"), errors="coerce", utc=True)
    selected_counts = (
        references["source_account"].astype("string").value_counts()
        if "source_account" in references.columns
        else pd.Series(dtype="int64")
    )
    total_accounts = int(master["account"].nunique()) if "account" in master.columns else 0
    represented = int(selected_counts.size)
    max_share = (
        float(selected_counts.max() / len(references))
        if len(references) and not selected_counts.empty
        else 0.0
    )

    return {
        "dataset": {
            "posts": int(len(master)),
            "accounts": total_accounts,
            "date_min": None if created.isna().all() else created.min().isoformat(),
            "date_max": None if created.isna().all() else created.max().isoformat(),
            "content_types": _content_counts(master),
        },
        "performance": {
            "median_views": _median(master, "views"),
            "p95_views": _quantile(master, "views", 0.95),
            "p99_views": _quantile(master, "views", 0.99),
            "median_save_rate": _median(master, "save_rate"),
            "median_share_rate": _median(master, "share_rate"),
        },
        "reference_population": {
            "content_type": content_type,
            "posts": int(len(population)),
            "accounts": int(population["account"].nunique())
            if "account" in population.columns
            else 0,
        },
        "selection": {
            "strategy": strategy,
            "references": int(len(references)),
            "accounts_represented": represented,
            "accounts_total": total_accounts,
            "account_coverage": float(represented / total_accounts) if total_accounts else None,
            "max_account_share": max_share,
            "account_counts": {
                str(key): int(value) for key, value in selected_counts.sort_index().items()
            },
            "dimension_coverage": _dimension_coverage(population, references),
        },
        "accounts": _account_rows(master, population, references),
        "dimensions": {
            dimension: _dimension_summary(population, dimension)
            for dimension in SYSTEM_DIMENSIONS
            if dimension in population.columns
        },
    }
