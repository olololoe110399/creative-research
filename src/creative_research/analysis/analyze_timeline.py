#!/usr/bin/env python3
"""Build deterministic operator/account strategy timelines and change points.

This stage summarizes how observed content mix, cadence, relative performance, and
creative-family activity change across fixed historical windows. It does not ask an
LLM to label strategy. Change points are deterministic differences between adjacent
windows with explicit component evidence.
"""

from __future__ import annotations

import json
import math
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION

TIMELINE_SCHEMA_VERSION = "strategy-timeline-v1"

DIMENSIONS = (
    "hook_technique",
    "content_angle",
    "format",
    "audience_segment",
    "product_placement_style",
    "cta_type",
    "dominant_visual_type",
)

FREQUENCIES = {
    "month": "M",
    "week": "W-SUN",
}


def _clean(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "<na>"}:
        return None
    return text


def _numeric(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _median(values: list[float]) -> float | None:
    return float(pd.Series(values, dtype="float64").median()) if values else None


def _rate(values: list[bool]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _bool_values(values: pd.Series) -> list[bool]:
    result: list[bool] = []
    for value in values:
        if value is None or value is pd.NA:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        result.append(bool(value))
    return result


def _as_bool(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def _format_value(record: dict[str, Any]) -> str | None:
    content_format = _clean(record.get("content_format"))
    video_format = _clean(record.get("video_format"))
    return content_format or video_format


def _distribution(values: pd.Series) -> dict[str, float]:
    clean = values.map(_clean).dropna()
    if clean.empty:
        return {}
    counts = clean.value_counts()
    total = int(counts.sum())
    return {str(key): float(value / total) for key, value in counts.sort_index().items()}


def _top_value(distribution: dict[str, float]) -> tuple[str | None, float | None]:
    if not distribution:
        return None, None
    value, share = sorted(
        distribution.items(),
        key=lambda item: (-item[1], item[0]),
    )[0]
    return value, float(share)


def _tvd(
    left: dict[str, float],
    right: dict[str, float],
) -> float | None:
    if not left and not right:
        return None
    keys = set(left) | set(right)
    return float(0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys))


def _safe_abs_delta(left: Any, right: Any) -> float | None:
    a = _numeric(left)
    b = _numeric(right)
    if a is None or b is None:
        return None
    return abs(b - a)


def _intensity_delta(left: Any, right: Any) -> float | None:
    a = _numeric(left)
    b = _numeric(right)
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    return float(min(1.0, abs(math.log(b / a)) / math.log(4.0)))


def _weighted_mean(parts: list[tuple[float | None, float]]) -> float | None:
    available = [(value, weight) for value, weight in parts if value is not None]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return float(sum(float(value) * weight for value, weight in available) / total_weight)


def _window_period(
    timestamp: pd.Series,
    *,
    frequency: str,
    timezone: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    if frequency not in FREQUENCIES:
        raise ValueError(f"Unknown frequency {frequency!r}; expected one of {sorted(FREQUENCIES)}")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc

    utc = pd.to_datetime(timestamp, errors="coerce", utc=True)
    local = utc.dt.tz_convert(zone)
    naive_local = local.dt.tz_localize(None)
    periods = naive_local.dt.to_period(FREQUENCIES[frequency])
    start_naive = periods.dt.start_time
    end_naive = periods.dt.end_time

    start_local = start_naive.dt.tz_localize(zone, ambiguous="NaT", nonexistent="shift_forward")
    end_local = end_naive.dt.tz_localize(zone, ambiguous="NaT", nonexistent="shift_forward")
    period_id = periods.astype("string").where(periods.notna())
    return period_id, start_local, end_local


def _join_base(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    performance: pd.DataFrame | None,
    cadence: pd.DataFrame | None,
) -> pd.DataFrame:
    required = {
        "post_uid",
        "operator_id",
        "account_id",
        "account",
        "created_at",
        "content_type",
    }
    missing = sorted(required - set(posts.columns))
    if missing:
        raise ValueError(f"posts table missing required columns: {', '.join(missing)}")
    if "post_uid" not in analysis.columns:
        raise ValueError("creative_analysis table missing required column: post_uid")
    if posts["post_uid"].duplicated().any():
        raise ValueError("posts table must contain unique post_uid values")
    if analysis["post_uid"].duplicated().any():
        raise ValueError("creative_analysis table must contain unique post_uid values")

    analysis_cols = [
        "post_uid",
        "hook_technique",
        "content_angle",
        "content_format",
        "video_format",
        "audience_segment",
        "product_placement_style",
        "cta_type",
        "dominant_visual_type",
        "has_product",
        "has_cta",
    ]
    present_analysis = [column for column in analysis_cols if column in analysis.columns]
    work = posts.merge(
        analysis[present_analysis],
        on="post_uid",
        how="left",
        suffixes=("", "_analysis"),
    )

    work["format"] = [_format_value(record) for record in work.to_dict(orient="records")]

    if performance is not None and not performance.empty and "post_uid" in performance.columns:
        perf_cols = [
            column
            for column in (
                "post_uid",
                "views_percentile_account",
                "views_percentile_operator",
                "views_tier_account",
            )
            if column in performance.columns
        ]
        work = work.merge(performance[perf_cols], on="post_uid", how="left")

    if cadence is not None and not cadence.empty and "post_uid" in cadence.columns:
        cadence_cols = [
            column
            for column in (
                "post_uid",
                "gap_from_previous_account_hours",
                "gap_from_previous_operator_hours",
                "posts_previous_24h_operator",
                "posts_previous_7d_operator",
            )
            if column in cadence.columns
        ]
        work = work.merge(cadence[cadence_cols], on="post_uid", how="left")

    return work


def _family_features(
    family_members: pd.DataFrame | None,
) -> dict[str, dict[str, Any]]:
    if family_members is None or family_members.empty:
        return {}
    required = {"post_uid", "family_id", "is_family_origin"}
    if not required.issubset(family_members.columns):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in family_members.to_dict(orient="records"):
        result[str(row["post_uid"])] = {
            "family_id": _clean(row.get("family_id")),
            "is_family_origin": _as_bool(row.get("is_family_origin", False)),
        }
    return result


def _entry_features(
    family_entries: pd.DataFrame | None,
) -> dict[str, dict[str, Any]]:
    if family_entries is None or family_entries.empty:
        return {}
    if "first_post_uid_on_account" not in family_entries.columns:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in family_entries.to_dict(orient="records"):
        post_uid = str(row.get("first_post_uid_on_account") or "")
        if not post_uid:
            continue
        result[post_uid] = {
            "is_family_account_entry": True,
            "is_origin_account_entry": _as_bool(row.get("is_origin_account", False)),
            "entry_order": row.get("entry_order"),
        }
    return result


def _enrich_family_activity(
    work: pd.DataFrame,
    family_members: pd.DataFrame | None,
    family_entries: pd.DataFrame | None,
) -> pd.DataFrame:
    member_lookup = _family_features(family_members)
    entry_lookup = _entry_features(family_entries)
    result = work.copy()
    result["family_id"] = [
        member_lookup.get(str(uid), {}).get("family_id") for uid in result["post_uid"]
    ]
    result["is_family_origin"] = [
        bool(member_lookup.get(str(uid), {}).get("is_family_origin", False))
        for uid in result["post_uid"]
    ]
    result["is_family_account_entry"] = [
        bool(entry_lookup.get(str(uid), {}).get("is_family_account_entry", False))
        for uid in result["post_uid"]
    ]
    result["is_origin_account_entry"] = [
        bool(entry_lookup.get(str(uid), {}).get("is_origin_account_entry", False))
        for uid in result["post_uid"]
    ]
    result["is_imported_family_entry"] = (
        result["is_family_account_entry"] & ~result["is_origin_account_entry"]
    )
    return result


def _group_window_row(
    group: pd.DataFrame,
    *,
    scope_type: str,
    scope_id: str,
    period_id: str,
    window_start: Any,
    window_end: Any,
    timezone: str,
) -> dict[str, Any]:
    created = pd.to_datetime(group["created_at"], errors="coerce", utc=True)
    zone = ZoneInfo(timezone)
    local_created = created.dt.tz_convert(zone)
    active_days = int(local_created.dt.strftime("%Y-%m-%d").nunique())
    posts_per_active_day = float(len(group) / active_days) if active_days else None

    row: dict[str, Any] = {
        "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
        "timeline_schema_version": TIMELINE_SCHEMA_VERSION,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "operator_id": (
            _clean(group["operator_id"].iloc[0]) if "operator_id" in group.columns else None
        ),
        "account_id": (
            _clean(group["account_id"].iloc[0])
            if scope_type == "account" and "account_id" in group.columns
            else None
        ),
        "account": (
            _clean(group["account"].iloc[0])
            if scope_type == "account" and "account" in group.columns
            else None
        ),
        "period_id": period_id,
        "window_start_local": window_start,
        "window_end_local": window_end,
        "timezone": timezone,
        "posts": int(len(group)),
        "active_days": active_days,
        "posts_per_active_day": posts_per_active_day,
        "active_accounts": (int(group["account_id"].nunique()) if scope_type == "operator" else 1),
        "slideshow_share": _rate([str(value) == "slideshow" for value in group["content_type"]]),
        "video_share": _rate([str(value) == "video" for value in group["content_type"]]),
        "product_rate": _rate(
            _bool_values(group.get("has_product", pd.Series(pd.NA, index=group.index)))
        ),
        "cta_rate": _rate(_bool_values(group.get("has_cta", pd.Series(pd.NA, index=group.index)))),
        "family_origins": int(
            group.get("is_family_origin", pd.Series(False, index=group.index))
            .fillna(False)
            .astype(bool)
            .sum()
        ),
        "family_account_entries": int(
            group.get("is_family_account_entry", pd.Series(False, index=group.index))
            .fillna(False)
            .astype(bool)
            .sum()
        ),
        "imported_family_entries": int(
            group.get("is_imported_family_entry", pd.Series(False, index=group.index))
            .fillna(False)
            .astype(bool)
            .sum()
        ),
        "families_observed": (
            int(group["family_id"].dropna().nunique()) if "family_id" in group.columns else 0
        ),
    }

    for metric in (
        "views_percentile_account",
        "views_percentile_operator",
        "gap_from_previous_account_hours",
        "gap_from_previous_operator_hours",
        "posts_previous_24h_operator",
    ):
        if metric in group.columns:
            values = [
                value for value in (_numeric(item) for item in group[metric]) if value is not None
            ]
            row[f"median_{metric}"] = _median(values)

    for dimension in DIMENSIONS:
        if dimension not in group.columns:
            distribution: dict[str, float] = {}
        else:
            distribution = _distribution(group[dimension])
        top, share = _top_value(distribution)
        row[f"{dimension}_distribution_json"] = _json(distribution)
        row[f"top_{dimension}"] = top
        row[f"top_{dimension}_share"] = share

    return row


def _build_windows_for_scope(
    work: pd.DataFrame,
    *,
    scope_type: str,
    frequency: str,
    timezone: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_col = "operator_id" if scope_type == "operator" else "account_id"
    valid = work.loc[
        work[group_col].notna() & work["_period_id"].notna() & work["created_at"].notna()
    ].copy()

    rows: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []

    for (scope_id, period_id), group in valid.groupby(
        [group_col, "_period_id"],
        sort=True,
        dropna=True,
    ):
        start = group["_window_start_local"].iloc[0]
        end = group["_window_end_local"].iloc[0]
        rows.append(
            _group_window_row(
                group,
                scope_type=scope_type,
                scope_id=str(scope_id),
                period_id=str(period_id),
                window_start=start,
                window_end=end,
                timezone=timezone,
            )
        )
        for post_uid in group["post_uid"].astype(str):
            memberships.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "timeline_schema_version": TIMELINE_SCHEMA_VERSION,
                    "scope_type": scope_type,
                    "scope_id": str(scope_id),
                    "period_id": str(period_id),
                    "post_uid": post_uid,
                }
            )

    return pd.DataFrame(rows), pd.DataFrame(memberships)


def _parse_distribution(row: dict[str, Any], dimension: str) -> dict[str, float]:
    raw = row.get(f"{dimension}_distribution_json")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in parsed.items():
        number = _numeric(value)
        if number is not None:
            result[str(key)] = number
    return result


def _change_point_rows(
    windows: pd.DataFrame,
    *,
    min_posts: int,
    threshold: float,
) -> pd.DataFrame:
    if windows.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (scope_type, scope_id), group in windows.groupby(
        ["scope_type", "scope_id"],
        sort=True,
        dropna=True,
    ):
        group = group.sort_values("window_start_local", kind="mergesort").reset_index(drop=True)
        for index in range(1, len(group)):
            previous = group.iloc[index - 1].to_dict()
            current = group.iloc[index].to_dict()
            if (
                int(previous.get("posts", 0)) < min_posts
                or int(current.get("posts", 0)) < min_posts
            ):
                continue

            dimension_changes: dict[str, float] = {}
            for dimension in DIMENSIONS:
                value = _tvd(
                    _parse_distribution(previous, dimension),
                    _parse_distribution(current, dimension),
                )
                if value is not None:
                    dimension_changes[dimension] = value

            categorical_shift = (
                _mean(list(dimension_changes.values())) if dimension_changes else None
            )
            content_type_shift = _safe_abs_delta(
                previous.get("video_share"),
                current.get("video_share"),
            )
            product_shift = _safe_abs_delta(
                previous.get("product_rate"),
                current.get("product_rate"),
            )
            cta_shift = _safe_abs_delta(
                previous.get("cta_rate"),
                current.get("cta_rate"),
            )
            performance_shift = _safe_abs_delta(
                previous.get("median_views_percentile_account"),
                current.get("median_views_percentile_account"),
            )
            posting_shift = _intensity_delta(
                previous.get("posts_per_active_day"),
                current.get("posts_per_active_day"),
            )

            score = _weighted_mean(
                [
                    (categorical_shift, 0.45),
                    (content_type_shift, 0.10),
                    (product_shift, 0.10),
                    (cta_shift, 0.05),
                    (performance_shift, 0.10),
                    (posting_shift, 0.20),
                ]
            )
            if score is None:
                continue

            changed_dimensions = [
                dimension for dimension, value in dimension_changes.items() if value >= 0.25
            ]
            scalar_changes = {
                "content_type": content_type_shift,
                "product_rate": product_shift,
                "cta_rate": cta_shift,
                "performance": performance_shift,
                "posting_intensity": posting_shift,
            }
            changed_dimensions.extend(
                key for key, value in scalar_changes.items() if value is not None and value >= 0.20
            )

            rows.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "timeline_schema_version": TIMELINE_SCHEMA_VERSION,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "operator_id": current.get("operator_id"),
                    "account_id": current.get("account_id"),
                    "previous_period_id": previous.get("period_id"),
                    "current_period_id": current.get("period_id"),
                    "change_at": current.get("window_start_local"),
                    "previous_posts": int(previous.get("posts", 0)),
                    "current_posts": int(current.get("posts", 0)),
                    "change_score": score,
                    "is_change_point": bool(score >= threshold),
                    "changed_dimensions_json": _json(sorted(set(changed_dimensions))),
                    "dimension_tvd_json": _json(dimension_changes),
                    "scalar_changes_json": _json(scalar_changes),
                    "previous_window_json": _json(previous),
                    "current_window_json": _json(current),
                    "threshold": threshold,
                    "min_posts": min_posts,
                }
            )

    return pd.DataFrame(rows)


def build_strategy_timeline_tables(
    posts: pd.DataFrame,
    analysis: pd.DataFrame,
    performance: pd.DataFrame | None = None,
    cadence: pd.DataFrame | None = None,
    family_members: pd.DataFrame | None = None,
    family_entries: pd.DataFrame | None = None,
    *,
    frequency: str = "month",
    timezone: str = "UTC",
    min_posts: int = 5,
    change_threshold: float = 0.24,
) -> dict[str, pd.DataFrame]:
    work = _join_base(posts, analysis, performance, cadence)
    work = _enrich_family_activity(work, family_members, family_entries)
    period_id, start, end = _window_period(
        work["created_at"],
        frequency=frequency,
        timezone=timezone,
    )
    work["_period_id"] = period_id
    work["_window_start_local"] = start
    work["_window_end_local"] = end

    operator_windows, operator_members = _build_windows_for_scope(
        work,
        scope_type="operator",
        frequency=frequency,
        timezone=timezone,
    )
    account_windows, account_members = _build_windows_for_scope(
        work,
        scope_type="account",
        frequency=frequency,
        timezone=timezone,
    )
    windows = pd.concat(
        [operator_windows, account_windows],
        ignore_index=True,
        sort=False,
    )
    memberships = pd.concat(
        [operator_members, account_members],
        ignore_index=True,
        sort=False,
    )
    changes = _change_point_rows(
        windows,
        min_posts=min_posts,
        threshold=change_threshold,
    )
    return {
        "strategy_windows": windows,
        "strategy_window_members": memberships,
        "strategy_change_points": changes,
    }
