#!/usr/bin/env python3
"""Derive account- and operator-level posting cadence from canonical posts."""
from __future__ import annotations

import argparse
import json
from bisect import bisect_left
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION
from creative_research.validation import read_table

HOUR_NS = 60 * 60 * 1_000_000_000
DAY_NS = 24 * HOUR_NS


def _hours(delta: pd.Timedelta | None) -> float | None:
    if delta is None or pd.isna(delta):
        return None
    return float(delta.total_seconds() / 3600)


def _quantile(values: pd.Series, q: float) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return None if clean.empty else float(clean.quantile(q))


def _median(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return None if clean.empty else float(clean.median())


def _top_counts_json(values: pd.Series, limit: int = 5) -> str:
    counts = values.dropna().value_counts().head(limit)
    payload = [
        {"value": value.item() if hasattr(value, "item") else value, "posts": int(count)}
        for value, count in counts.items()
    ]
    return json.dumps(payload, ensure_ascii=False)


def _chronology_rows(
    posts: pd.DataFrame,
    *,
    group_col: str,
    prefix: str,
    include_neighbor_account: bool,
) -> pd.DataFrame:
    columns = [
        "post_uid",
        f"{prefix}_sequence_index",
        f"previous_post_uid_{prefix}",
        f"next_post_uid_{prefix}",
        f"gap_from_previous_{prefix}_hours",
        f"gap_to_next_{prefix}_hours",
        f"posts_previous_24h_{prefix}",
        f"posts_previous_7d_{prefix}",
    ]
    if include_neighbor_account:
        columns.extend(
            [
                f"previous_account_{prefix}",
                f"next_account_{prefix}",
            ]
        )

    valid = posts.loc[
        posts[group_col].notna() & posts["_created_at"].notna()
    ].copy()
    if valid.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for _, group in valid.groupby(group_col, sort=False, dropna=True):
        group = group.sort_values(["_created_at", "post_uid"], kind="mergesort")
        records = group.to_dict(orient="records")
        times_ns = [int(record["_created_at"].value) for record in records]

        for index, record in enumerate(records):
            current = record["_created_at"]
            previous = records[index - 1] if index > 0 else None
            next_item = records[index + 1] if index + 1 < len(records) else None

            lower_24h = bisect_left(
                times_ns,
                times_ns[index] - DAY_NS,
                0,
                index,
            )
            lower_7d = bisect_left(
                times_ns,
                times_ns[index] - 7 * DAY_NS,
                0,
                index,
            )

            row: dict[str, Any] = {
                "post_uid": record["post_uid"],
                f"{prefix}_sequence_index": index + 1,
                f"previous_post_uid_{prefix}": (
                    previous["post_uid"] if previous is not None else None
                ),
                f"next_post_uid_{prefix}": (
                    next_item["post_uid"] if next_item is not None else None
                ),
                f"gap_from_previous_{prefix}_hours": (
                    _hours(current - previous["_created_at"])
                    if previous is not None
                    else None
                ),
                f"gap_to_next_{prefix}_hours": (
                    _hours(next_item["_created_at"] - current)
                    if next_item is not None
                    else None
                ),
                f"posts_previous_24h_{prefix}": index - lower_24h,
                f"posts_previous_7d_{prefix}": index - lower_7d,
            }
            if include_neighbor_account:
                row[f"previous_account_{prefix}"] = (
                    previous.get("account") if previous is not None else None
                )
                row[f"next_account_{prefix}"] = (
                    next_item.get("account") if next_item is not None else None
                )
            rows.append(row)
    return pd.DataFrame(rows)


def build_posting_cadence(
    posts: pd.DataFrame,
    *,
    timezone: str = "UTC",
) -> pd.DataFrame:
    required = {"post_uid", "account_id", "account", "operator_id", "created_at"}
    missing = sorted(required - set(posts.columns))
    if missing:
        raise ValueError(f"posts table missing required columns: {', '.join(missing)}")

    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc

    work = posts.copy()
    work["_created_at"] = pd.to_datetime(work["created_at"], errors="coerce", utc=True)
    work = work.sort_values(
        ["_created_at", "account", "post_uid"],
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)

    output = pd.DataFrame(index=work.index)
    output["analytics_schema_version"] = ANALYTICS_SCHEMA_VERSION
    for column in (
        "post_uid",
        "operator_id",
        "account_id",
        "platform",
        "account",
        "post_id",
        "content_type",
    ):
        output[column] = work[column] if column in work.columns else pd.NA

    output["published_at_utc"] = work["_created_at"]
    local = work["_created_at"].dt.tz_convert(zone)
    output["published_at_local"] = local
    output["timezone"] = timezone
    output["local_date"] = local.dt.strftime("%Y-%m-%d")
    output["posting_hour_local"] = local.dt.hour.astype("Int64")
    output["weekday_index_local"] = local.dt.weekday.astype("Int64")
    output["weekday_local"] = local.dt.day_name()

    valid_local = output["local_date"].notna()
    output["post_number_account_local_day"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["posts_account_local_day"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    if valid_local.any():
        local_groups = output.loc[valid_local].groupby(
            ["account_id", "local_date"], sort=False, dropna=False
        )
        output.loc[valid_local, "post_number_account_local_day"] = (
            local_groups.cumcount() + 1
        ).astype("Int64")
        output.loc[valid_local, "posts_account_local_day"] = local_groups[
            "post_uid"
        ].transform("size").astype("Int64")

    account_chronology = _chronology_rows(
        work,
        group_col="account_id",
        prefix="account",
        include_neighbor_account=False,
    )
    operator_chronology = _chronology_rows(
        work,
        group_col="operator_id",
        prefix="operator",
        include_neighbor_account=True,
    )

    output = output.merge(account_chronology, on="post_uid", how="left")
    output = output.merge(operator_chronology, on="post_uid", how="left")

    valid_operator_day = output["operator_id"].notna() & output["local_date"].notna()
    output["post_number_operator_local_day"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["posts_operator_local_day"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    if valid_operator_day.any():
        operator_day_groups = output.loc[valid_operator_day].groupby(
            ["operator_id", "local_date"], sort=False, dropna=False
        )
        output.loc[valid_operator_day, "post_number_operator_local_day"] = (
            operator_day_groups.cumcount() + 1
        ).astype("Int64")
        output.loc[valid_operator_day, "posts_operator_local_day"] = operator_day_groups[
            "post_uid"
        ].transform("size").astype("Int64")

    return output


def build_account_activity_daily(cadence: pd.DataFrame) -> pd.DataFrame:
    work = cadence.loc[cadence["local_date"].notna()].copy()
    rows: list[dict[str, Any]] = []
    for (_, local_date), group in work.groupby(
        ["account_id", "local_date"], sort=True, dropna=False
    ):
        group = group.sort_values("published_at_local", kind="mergesort")
        first = group["published_at_local"].iloc[0]
        last = group["published_at_local"].iloc[-1]
        diffs = group["published_at_local"].diff().dropna()
        rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "operator_id": group["operator_id"].iloc[0],
                "account_id": group["account_id"].iloc[0],
                "account": group["account"].iloc[0],
                "local_date": local_date,
                "timezone": group["timezone"].iloc[0],
                "posts": int(len(group)),
                "slideshow_posts": int((group["content_type"] == "slideshow").sum()),
                "video_posts": int((group["content_type"] == "video").sum()),
                "first_post_local": first,
                "last_post_local": last,
                "active_span_hours": _hours(last - first),
                "median_gap_within_day_hours": (
                    float(diffs.dt.total_seconds().median() / 3600)
                    if not diffs.empty
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


def build_operator_activity_daily(cadence: pd.DataFrame) -> pd.DataFrame:
    work = cadence.loc[
        cadence["operator_id"].notna() & cadence["local_date"].notna()
    ].copy()
    rows: list[dict[str, Any]] = []
    for (operator_id, local_date), group in work.groupby(
        ["operator_id", "local_date"], sort=True, dropna=True
    ):
        group = group.sort_values("published_at_local", kind="mergesort")
        first = group["published_at_local"].iloc[0]
        last = group["published_at_local"].iloc[-1]
        accounts = group["account"].astype("string")
        transitions = max(0, len(group) - 1)
        switches = int(accounts.ne(accounts.shift()).sum() - (1 if len(group) else 0))
        rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "operator_id": operator_id,
                "local_date": local_date,
                "timezone": group["timezone"].iloc[0],
                "posts": int(len(group)),
                "accounts_active": int(group["account_id"].nunique()),
                "account_switches": switches,
                "account_switch_rate": (
                    float(switches / transitions) if transitions else None
                ),
                "first_post_local": first,
                "last_post_local": last,
                "active_span_hours": _hours(last - first),
            }
        )
    return pd.DataFrame(rows)


def _cadence_summary(
    cadence: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    group_col: str,
    level: str,
    gap_col: str,
) -> pd.DataFrame:
    work = cadence.loc[cadence[group_col].notna() & cadence["published_at_utc"].notna()]
    rows: list[dict[str, Any]] = []
    for group_value, group in work.groupby(group_col, sort=True, dropna=True):
        day_rows = daily.loc[daily[group_col] == group_value]
        gaps = pd.to_numeric(group[gap_col], errors="coerce")
        row: dict[str, Any] = {
            "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
            "cadence_level": level,
            group_col: group_value,
            "timezone": group["timezone"].iloc[0],
            "posts": int(len(group)),
            "active_days": int(group["local_date"].nunique()),
            "first_post_utc": group["published_at_utc"].min(),
            "last_post_utc": group["published_at_utc"].max(),
            "median_gap_hours": _median(gaps),
            "p25_gap_hours": _quantile(gaps, 0.25),
            "p75_gap_hours": _quantile(gaps, 0.75),
            "p90_gap_hours": _quantile(gaps, 0.90),
            "median_posts_per_active_day": (
                _median(day_rows["posts"]) if not day_rows.empty else None
            ),
            "max_posts_per_active_day": (
                int(day_rows["posts"].max()) if not day_rows.empty else None
            ),
            "top_posting_hours_json": _top_counts_json(group["posting_hour_local"]),
            "top_weekdays_json": _top_counts_json(group["weekday_local"]),
        }
        if level == "account":
            row["operator_id"] = group["operator_id"].iloc[0]
            row["account"] = group["account"].iloc[0]
        else:
            row["accounts"] = int(group["account_id"].nunique())
            if not day_rows.empty and "account_switch_rate" in day_rows.columns:
                row["median_daily_account_switch_rate"] = _median(
                    day_rows["account_switch_rate"]
                )
        rows.append(row)
    return pd.DataFrame(rows)


def build_cadence_tables(
    posts: pd.DataFrame,
    *,
    timezone: str = "UTC",
) -> dict[str, pd.DataFrame]:
    cadence = build_posting_cadence(posts, timezone=timezone)
    account_daily = build_account_activity_daily(cadence)
    operator_daily = build_operator_activity_daily(cadence)
    return {
        "posting_cadence": cadence,
        "account_activity_daily": account_daily,
        "operator_activity_daily": operator_daily,
        "account_cadence_summary": _cadence_summary(
            cadence,
            account_daily,
            group_col="account_id",
            level="account",
            gap_col="gap_from_previous_account_hours",
        ),
        "operator_cadence_summary": _cadence_summary(
            cadence,
            operator_daily,
            group_col="operator_id",
            level="operator",
            gap_col="gap_from_previous_operator_hours",
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive historical posting cadence at account and operator level. "
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
    parser.add_argument(
        "--timezone",
        default="UTC",
        help="Timezone used for posting-hour/day analysis (for example Asia/Ho_Chi_Minh).",
    )
    args = parser.parse_args()

    posts_path = Path(args.posts).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    posts = read_table(posts_path)
    tables = build_cadence_tables(posts, timezone=args.timezone)

    outputs: dict[str, str] = {}
    for name, table in tables.items():
        path = out_dir / f"{name}.parquet"
        table.to_parquet(path, index=False)
        outputs[name] = str(path)

    report = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(posts_path),
        "timezone": args.timezone,
        "posts": int(len(posts)),
        "posts_with_timestamp": int(
            pd.to_datetime(posts["created_at"], errors="coerce", utc=True).notna().sum()
        ),
        "outputs": outputs,
        "notes": [
            "No scrape was performed.",
            "No realtime metrics were collected.",
            "No LLM/Vision call was performed.",
            "Posting time is converted from stored UTC timestamps into the selected analysis timezone.",
        ],
    }
    (out_dir / "cadence_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
