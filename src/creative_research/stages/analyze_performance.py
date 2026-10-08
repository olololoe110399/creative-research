#!/usr/bin/env python3
"""Build deterministic relative-performance baselines from canonical posts.

This stage is offline. It reads data/05_master/posts.parquet and derives
account/operator/global relative performance without scraping or calling an LLM.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.validation import read_table

METRICS = ("views", "likes", "comments", "shares", "saves")


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Float64")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = _numeric(numerator)
    den = _numeric(denominator)
    valid = num.notna() & den.notna() & den.ne(0)
    result = pd.Series(pd.NA, index=num.index, dtype="Float64")
    result.loc[valid] = num.loc[valid] / den.loc[valid]
    return result


def _tier(percentile: Any) -> str | None:
    if percentile is None or percentile is pd.NA:
        return None
    try:
        if pd.isna(percentile):
            return None
    except (TypeError, ValueError):
        return None
    value = float(percentile)
    if value >= 0.95:
        return "top_5"
    if value >= 0.80:
        return "top_20"
    if value <= 0.20:
        return "bottom_20"
    return "middle_60"


def _group_rank(
    work: pd.DataFrame,
    metric_col: str,
    group_col: str,
    *,
    allow_missing_group: bool,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    values = work[metric_col]
    percentile = pd.Series(pd.NA, index=work.index, dtype="Float64")
    median = pd.Series(pd.NA, index=work.index, dtype="Float64")
    count = pd.Series(pd.NA, index=work.index, dtype="Int64")

    mask = values.notna()
    if not allow_missing_group:
        mask &= work[group_col].notna()
    if not mask.any():
        return percentile, median, count

    subset = work.loc[mask, [group_col, metric_col]].copy()
    grouped = subset.groupby(group_col, dropna=allow_missing_group)[metric_col]
    percentile.loc[subset.index] = grouped.rank(method="average", pct=True).astype("Float64")
    median.loc[subset.index] = grouped.transform("median").astype("Float64")
    count.loc[subset.index] = grouped.transform("count").astype("Int64")
    return percentile, median, count


def build_post_performance(posts: pd.DataFrame) -> pd.DataFrame:
    required = {"post_uid", "account_id", "account", "operator_id"}
    missing = sorted(required - set(posts.columns))
    if missing:
        raise ValueError(f"posts table missing required columns: {', '.join(missing)}")

    work = posts.copy()
    output = pd.DataFrame(index=work.index)
    identity_cols = [
        "post_uid",
        "operator_id",
        "account_id",
        "platform",
        "account",
        "post_id",
        "created_at",
        "content_type",
    ]
    for column in identity_cols:
        output[column] = work[column] if column in work.columns else pd.NA
    output.insert(0, "analytics_schema_version", ANALYTICS_SCHEMA_VERSION)

    for metric in METRICS:
        source = work[metric] if metric in work.columns else pd.Series(pd.NA, index=work.index)
        numeric_col = f"_{metric}"
        work[numeric_col] = _numeric(source)
        output[metric] = work[numeric_col]

        account_pct, account_median, account_n = _group_rank(
            work, numeric_col, "account_id", allow_missing_group=True
        )
        operator_pct, operator_median, operator_n = _group_rank(
            work, numeric_col, "operator_id", allow_missing_group=False
        )

        output[f"{metric}_percentile_account"] = account_pct
        output[f"{metric}_vs_account_median"] = _safe_ratio(
            work[numeric_col], account_median
        )
        output[f"{metric}_account_sample_size"] = account_n

        output[f"{metric}_percentile_operator"] = operator_pct
        output[f"{metric}_vs_operator_median"] = _safe_ratio(
            work[numeric_col], operator_median
        )
        output[f"{metric}_operator_sample_size"] = operator_n

        global_pct = pd.Series(pd.NA, index=work.index, dtype="Float64")
        valid = work[numeric_col].notna()
        if valid.any():
            global_pct.loc[valid] = work.loc[valid, numeric_col].rank(
                method="average", pct=True
            )
        output[f"{metric}_percentile_global"] = global_pct

    views = work["_views"]
    for metric in ("likes", "comments", "shares", "saves"):
        output[f"{metric[:-1] if metric.endswith('s') else metric}_rate_by_view"] = _safe_ratio(
            work[f"_{metric}"], views
        )

    output["views_tier_account"] = output["views_percentile_account"].map(_tier)
    output["views_tier_operator"] = output["views_percentile_operator"].map(_tier)

    return output


def _quantile(values: pd.Series, q: float) -> float | None:
    clean = _numeric(values).dropna()
    return None if clean.empty else float(clean.quantile(q))


def _median(values: pd.Series) -> float | None:
    clean = _numeric(values).dropna()
    return None if clean.empty else float(clean.median())


def _max(values: pd.Series) -> float | None:
    clean = _numeric(values).dropna()
    return None if clean.empty else float(clean.max())


def _baseline_rows(
    posts: pd.DataFrame,
    *,
    group_col: str,
    level: str,
) -> pd.DataFrame:
    required = {group_col}
    missing = sorted(required - set(posts.columns))
    if missing:
        raise ValueError(f"posts table missing required columns: {', '.join(missing)}")

    work = posts.loc[posts[group_col].notna()].copy()
    rows: list[dict[str, Any]] = []
    for group_value, group in work.groupby(group_col, sort=True, dropna=True):
        row: dict[str, Any] = {
            "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
            "baseline_level": level,
            group_col: group_value,
            "posts": int(len(group)),
        }
        if level == "account":
            for column in ("operator_id", "account", "platform"):
                row[column] = group[column].iloc[0] if column in group.columns else None
        if level == "operator":
            row["accounts"] = (
                int(group["account_id"].nunique()) if "account_id" in group.columns else None
            )

        for metric in METRICS:
            if metric not in group.columns:
                continue
            values = _numeric(group[metric])
            row[f"{metric}_observed"] = int(values.notna().sum())
            row[f"median_{metric}"] = _median(values)
            row[f"p25_{metric}"] = _quantile(values, 0.25)
            row[f"p75_{metric}"] = _quantile(values, 0.75)
            row[f"p90_{metric}"] = _quantile(values, 0.90)
            row[f"p95_{metric}"] = _quantile(values, 0.95)
            row[f"max_{metric}"] = _max(values)
        rows.append(row)
    return pd.DataFrame(rows)


def build_performance_tables(posts: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "post_performance": build_post_performance(posts),
        "account_performance_baselines": _baseline_rows(
            posts, group_col="account_id", level="account"
        ),
        "operator_performance_baselines": _baseline_rows(
            posts, group_col="operator_id", level="operator"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive relative performance baselines from canonical posts. "
            "No scrape, realtime collection, or LLM call is performed."
        )
    )
    parser.add_argument(
        "posts",
        nargs="?",
        default="data/05_master/posts.parquet",
        help="Canonical posts parquet/csv/jsonl.",
    )
    parser.add_argument("--out", default="data/06_analytics")
    args = parser.parse_args()

    posts_path = Path(args.posts).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    posts = read_table(posts_path)
    tables = build_performance_tables(posts)

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        table.to_parquet(path, index=False)
        outputs[name] = str(path)

    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(posts_path),
        "posts": int(len(posts)),
        "accounts": int(posts["account_id"].nunique()) if "account_id" in posts.columns else 0,
        "operators": int(posts["operator_id"].nunique()) if "operator_id" in posts.columns else 0,
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No realtime metrics were collected.",
            "No LLM/Vision call was performed.",
            "Percentiles are relative to the observed historical dataset.",
        ],
    }
    (out_dir / "performance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
