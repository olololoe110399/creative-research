#!/usr/bin/env python3
"""Derive cross-account creative-family propagation and account-role evidence.

This stage is deterministic and offline. It turns creative-family chronology into:
- first appearance of each family on each verified account;
- observed cross-account family propagation events;
- aggregated account-to-account propagation edges;
- descriptive account-role evidence features.

It does not assign strategic roles such as "testing" or "scaling". Those are later
hypotheses that must be supported by repeated evidence.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pandas as pd

from creative_research.constants import ANALYTICS_SCHEMA_VERSION

PROPAGATION_SCHEMA_VERSION = "creative-propagation-v2"

CHANGE_DIMENSIONS = (
    "content_type",
    "topic",
    "content_angle",
    "audience_segment",
    "product_family",
    "hook_technique",
    "format",
    "hook_text",
    "hook_replicable_formula",
    "creative_formula",
    "sequence_roles",
)


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


def _float(value: Any) -> float | None:
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


def _timestamp(value: Any) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed


def _days_between(left: Any, right: Any) -> float | None:
    first = _timestamp(left)
    second = _timestamp(right)
    if first is None or second is None:
        return None
    return float((second - first).total_seconds() / 86400)


def _hours_between(left: Any, right: Any) -> float | None:
    first = _timestamp(left)
    second = _timestamp(right)
    if first is None or second is None:
        return None
    return float((second - first).total_seconds() / 3600)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(pd.Series(values, dtype="float64").median())


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(pd.Series(values, dtype="float64").quantile(q))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return float(sum(1 for value in values if value) / len(values))


def _format_value(record: dict[str, Any]) -> str | None:
    content_format = _clean(record.get("content_format"))
    video_format = _clean(record.get("video_format"))
    return content_format or video_format


def _parse_sequence_roles(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if not isinstance(value, str) or not value.strip():
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item).strip() for item in parsed if str(item).strip())


def _analysis_lookup(analysis: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if analysis is None or analysis.empty or "post_uid" not in analysis.columns:
        return {}
    return {str(row["post_uid"]): row for row in analysis.to_dict(orient="records")}


def _performance_lookup(performance: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if performance is None or performance.empty or "post_uid" not in performance.columns:
        return {}
    return {str(row["post_uid"]): row for row in performance.to_dict(orient="records")}


def _member_features(
    member: dict[str, Any],
    analysis_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    analysis = analysis_lookup.get(str(member.get("post_uid")), {})
    return {
        "content_type": _clean(member.get("content_type") or analysis.get("content_type")),
        "topic": _clean(member.get("topic") or analysis.get("topic")),
        "content_angle": _clean(member.get("content_angle") or analysis.get("content_angle")),
        "audience_segment": _clean(analysis.get("audience_segment")),
        "product_family": _clean(analysis.get("product_family")),
        "hook_technique": _clean(analysis.get("hook_technique")),
        "format": _format_value(analysis),
        "hook_text": _clean(member.get("hook_text") or analysis.get("hook_text")),
        "hook_replicable_formula": _clean(
            member.get("hook_replicable_formula") or analysis.get("hook_replicable_formula")
        ),
        "creative_formula": _clean(
            member.get("creative_formula") or analysis.get("creative_formula")
        ),
        "sequence_roles": _parse_sequence_roles(member.get("sequence_roles_json")),
    }


def _change_summary(
    origin: dict[str, Any],
    target: dict[str, Any],
    analysis_lookup: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    left = _member_features(origin, analysis_lookup)
    right = _member_features(target, analysis_lookup)
    changed: list[str] = []
    preserved: list[str] = []
    unknown: list[str] = []

    for dimension in CHANGE_DIMENSIONS:
        left_value = left.get(dimension)
        right_value = right.get(dimension)
        left_missing = left_value in {None, "", ()}
        right_missing = right_value in {None, "", ()}
        if left_missing or right_missing:
            unknown.append(dimension)
        elif left_value == right_value:
            preserved.append(dimension)
        else:
            changed.append(dimension)
    return changed, preserved, unknown


def _validate_members(members: pd.DataFrame) -> None:
    required = {
        "family_id",
        "operator_id",
        "post_uid",
        "account_id",
        "account",
        "created_at",
        "is_family_origin",
        "family_origin_post_uid",
    }
    missing = sorted(required - set(members.columns))
    if missing:
        raise ValueError(f"creative_family_members missing required columns: {', '.join(missing)}")
    if members["post_uid"].duplicated().any():
        raise ValueError("creative_family_members must contain one row per post_uid")


def _ordered_family(group: pd.DataFrame) -> pd.DataFrame:
    work = group.copy()
    work["_created_at"] = pd.to_datetime(work["created_at"], errors="coerce", utc=True)
    work["_missing_time"] = work["_created_at"].isna()
    return work.sort_values(
        ["_missing_time", "_created_at", "family_member_index", "post_uid"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def _origin_record(group: pd.DataFrame) -> dict[str, Any]:
    origins = group.loc[group["is_family_origin"].fillna(False).astype(bool)]
    row = origins.iloc[0] if not origins.empty else group.iloc[0]
    return row.to_dict()


def build_family_account_entries(
    members: pd.DataFrame,
    performance: pd.DataFrame | None = None,
) -> pd.DataFrame:
    _validate_members(members)
    perf_lookup = _performance_lookup(performance)
    rows: list[dict[str, Any]] = []

    for family_id, raw_group in members.groupby("family_id", sort=True, dropna=True):
        group = _ordered_family(raw_group)
        origin = _origin_record(group)
        origin_account_id = str(origin["account_id"])
        origin_time = origin.get("_created_at") or _timestamp(origin.get("created_at"))

        first_entries: list[dict[str, Any]] = []
        for _account_id, account_group in group.groupby("account_id", sort=False, dropna=True):
            ordered = _ordered_family(account_group)
            first = ordered.iloc[0].to_dict()
            first_entries.append(first)

        first_entries.sort(
            key=lambda row: (
                pd.isna(row.get("_created_at")),
                row.get("_created_at")
                if not pd.isna(row.get("_created_at"))
                else pd.Timestamp.max.tz_localize("UTC"),
                str(row.get("post_uid")),
            )
        )

        for entry_index, first in enumerate(first_entries, start=1):
            account_id = str(first["account_id"])
            account_members = group.loc[group["account_id"].astype(str) == account_id]
            perf_values = [
                _float(perf_lookup.get(str(post_uid), {}).get("views_percentile_account"))
                for post_uid in account_members["post_uid"].astype(str)
            ]
            clean_perf = [value for value in perf_values if value is not None]
            first_perf = _float(
                perf_lookup.get(str(first["post_uid"]), {}).get("views_percentile_account")
            )
            rows.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "propagation_schema_version": PROPAGATION_SCHEMA_VERSION,
                    "family_id": str(family_id),
                    "operator_id": _clean(first.get("operator_id")),
                    "account_id": account_id,
                    "account": _clean(first.get("account")),
                    "entry_order": entry_index,
                    "is_origin_account": account_id == origin_account_id,
                    "family_origin_post_uid": str(origin["post_uid"]),
                    "family_origin_account_id": origin_account_id,
                    "family_origin_account": _clean(origin.get("account")),
                    "first_post_uid_on_account": str(first["post_uid"]),
                    "first_seen_on_account": first.get("_created_at"),
                    "days_since_family_origin": _days_between(
                        origin_time,
                        first.get("_created_at"),
                    ),
                    "posts_in_family_on_account": int(len(account_members)),
                    "first_post_views_percentile_account": first_perf,
                    "best_views_percentile_account": (max(clean_perf) if clean_perf else None),
                    "median_views_percentile_account": _median(clean_perf),
                }
            )

    return pd.DataFrame(rows)


def build_cross_account_propagation(
    members: pd.DataFrame,
    analysis: pd.DataFrame | None = None,
    performance: pd.DataFrame | None = None,
) -> pd.DataFrame:
    _validate_members(members)
    analysis_lookup = _analysis_lookup(analysis)
    perf_lookup = _performance_lookup(performance)
    rows: list[dict[str, Any]] = []

    for family_id, raw_group in members.groupby("family_id", sort=True, dropna=True):
        group = _ordered_family(raw_group)
        if group["account_id"].nunique() <= 1:
            continue

        origin = _origin_record(group)
        origin_account_id = str(origin["account_id"])
        origin_post_uid = str(origin["post_uid"])
        origin_time = origin.get("_created_at") or _timestamp(origin.get("created_at"))
        origin_perf = _float(perf_lookup.get(origin_post_uid, {}).get("views_percentile_account"))

        distinct_entries: list[dict[str, Any]] = []
        for account_id, account_group in group.groupby("account_id", sort=False, dropna=True):
            if str(account_id) == origin_account_id:
                continue
            ordered_target = _ordered_family(account_group)
            first_target = ordered_target.iloc[0].to_dict()
            distinct_entries.append(first_target)

        distinct_entries.sort(
            key=lambda row: (
                pd.isna(row.get("_created_at")),
                row.get("_created_at")
                if not pd.isna(row.get("_created_at"))
                else pd.Timestamp.max.tz_localize("UTC"),
                str(row.get("post_uid")),
            )
        )

        for entry_order, target in enumerate(distinct_entries, start=2):
            target_account_id = str(target["account_id"])
            target_post_uid = str(target["post_uid"])
            target_time = target.get("_created_at") or _timestamp(target.get("created_at"))

            target_position = int(group.index[group["post_uid"].astype(str).eq(target_post_uid)][0])
            preceding: dict[str, Any] | None = None
            for position in range(target_position - 1, -1, -1):
                candidate = group.iloc[position].to_dict()
                if str(candidate["account_id"]) != target_account_id:
                    preceding = candidate
                    break

            changed, preserved, unknown = _change_summary(
                origin,
                target,
                analysis_lookup,
            )
            target_account_members = group.loc[
                group["account_id"].astype(str).eq(target_account_id)
            ]
            target_perf_values = [
                _float(perf_lookup.get(str(uid), {}).get("views_percentile_account"))
                for uid in target_account_members["post_uid"].astype(str)
            ]
            clean_target_perf = [value for value in target_perf_values if value is not None]
            target_perf = _float(
                perf_lookup.get(target_post_uid, {}).get("views_percentile_account")
            )
            performance_delta = (
                target_perf - origin_perf
                if target_perf is not None and origin_perf is not None
                else None
            )

            rows.append(
                {
                    "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                    "propagation_schema_version": PROPAGATION_SCHEMA_VERSION,
                    "family_id": str(family_id),
                    "operator_id": _clean(target.get("operator_id")),
                    "family_origin_post_uid": origin_post_uid,
                    "origin_account_id": origin_account_id,
                    "origin_account": _clean(origin.get("account")),
                    "origin_created_at": origin_time,
                    "origin_views_percentile_account": origin_perf,
                    "target_entry_order": entry_order,
                    "target_account_id": target_account_id,
                    "target_account": _clean(target.get("account")),
                    "target_first_post_uid": target_post_uid,
                    "target_first_seen": target_time,
                    "delay_from_family_origin_hours": _hours_between(
                        origin_time,
                        target_time,
                    ),
                    "delay_from_family_origin_days": _days_between(
                        origin_time,
                        target_time,
                    ),
                    "preceding_family_post_uid": (
                        str(preceding["post_uid"]) if preceding is not None else None
                    ),
                    "preceding_account_id": (
                        str(preceding["account_id"]) if preceding is not None else None
                    ),
                    "preceding_account": (
                        _clean(preceding.get("account")) if preceding is not None else None
                    ),
                    "delay_from_preceding_family_post_hours": (
                        _hours_between(preceding.get("_created_at"), target_time)
                        if preceding is not None
                        else None
                    ),
                    "target_posts_in_family": int(len(target_account_members)),
                    "target_first_views_percentile_account": target_perf,
                    "target_best_views_percentile_account": (
                        max(clean_target_perf) if clean_target_perf else None
                    ),
                    "target_vs_origin_views_percentile_delta": performance_delta,
                    "target_outperformed_origin": (
                        target_perf > origin_perf
                        if target_perf is not None and origin_perf is not None
                        else None
                    ),
                    "match_score_to_origin": _float(target.get("match_score_to_origin")),
                    "match_score_to_nearest_member": _float(
                        target.get("match_score_to_nearest_member")
                    ),
                    "changed_dimensions_count": len(changed),
                    "changed_dimensions_json": json.dumps(changed, ensure_ascii=False),
                    "preserved_dimensions_json": json.dumps(preserved, ensure_ascii=False),
                    "unknown_dimensions_json": json.dumps(unknown, ensure_ascii=False),
                    "cross_content_type": (
                        _clean(origin.get("content_type")) != _clean(target.get("content_type"))
                    ),
                }
            )

    return pd.DataFrame(rows)


def _changed_dimension_counts(events: pd.DataFrame) -> str:
    counts: Counter[str] = Counter()
    if "changed_dimensions_json" not in events.columns:
        return json.dumps({}, ensure_ascii=False)
    for raw in events["changed_dimensions_json"]:
        if not isinstance(raw, str):
            continue
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(values, list):
            counts.update(str(value) for value in values)
    return json.dumps(dict(sorted(counts.items())), ensure_ascii=False, sort_keys=True)


def build_account_propagation_edges(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (
        operator_id,
        origin_account_id,
        target_account_id,
    ), group in events.groupby(
        ["operator_id", "origin_account_id", "target_account_id"],
        sort=True,
        dropna=True,
    ):
        delays = [
            value
            for value in (_float(item) for item in group["delay_from_family_origin_days"])
            if value is not None
        ]
        performance_deltas = [
            value
            for value in (_float(item) for item in group["target_vs_origin_views_percentile_delta"])
            if value is not None
        ]
        outperform_values = [
            bool(item)
            for item in group["target_outperformed_origin"]
            if item is not None and not pd.isna(item)
        ]
        rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "propagation_schema_version": PROPAGATION_SCHEMA_VERSION,
                "operator_id": operator_id,
                "origin_account_id": origin_account_id,
                "origin_account": _clean(group["origin_account"].iloc[0]),
                "target_account_id": target_account_id,
                "target_account": _clean(group["target_account"].iloc[0]),
                "families_observed": int(group["family_id"].nunique()),
                "propagation_events": int(len(group)),
                "median_delay_days": _median(delays),
                "p25_delay_days": _quantile(delays, 0.25),
                "p75_delay_days": _quantile(delays, 0.75),
                "median_target_vs_origin_performance_delta": _median(performance_deltas),
                "target_outperformed_origin_rate": _rate(outperform_values),
                "cross_content_type_rate": _rate(
                    [bool(value) for value in group["cross_content_type"]]
                ),
                "changed_dimension_counts_json": _changed_dimension_counts(group),
                "example_family_ids_json": json.dumps(
                    sorted(group["family_id"].astype(str).unique())[:20],
                    ensure_ascii=False,
                ),
            }
        )
    return pd.DataFrame(rows)


def build_account_sequence_edges(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()

    work = events.loc[
        events["preceding_account_id"].notna()
        & events["target_account_id"].notna()
        & events["preceding_account_id"].astype(str).ne(events["target_account_id"].astype(str))
    ].copy()
    if work.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (
        operator_id,
        preceding_account_id,
        target_account_id,
    ), group in work.groupby(
        ["operator_id", "preceding_account_id", "target_account_id"],
        sort=True,
        dropna=True,
    ):
        delays = [
            value
            for value in (_float(item) for item in group["delay_from_preceding_family_post_hours"])
            if value is not None
        ]
        rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "propagation_schema_version": PROPAGATION_SCHEMA_VERSION,
                "operator_id": operator_id,
                "preceding_account_id": preceding_account_id,
                "preceding_account": _clean(group["preceding_account"].iloc[0]),
                "target_account_id": target_account_id,
                "target_account": _clean(group["target_account"].iloc[0]),
                "observed_family_entries": int(len(group)),
                "families_observed": int(group["family_id"].nunique()),
                "median_delay_hours": _median(delays),
                "p25_delay_hours": _quantile(delays, 0.25),
                "p75_delay_hours": _quantile(delays, 0.75),
                "example_family_ids_json": json.dumps(
                    sorted(group["family_id"].astype(str).unique())[:20],
                    ensure_ascii=False,
                ),
                "interpretation": (
                    "nearest_prior_observed_family_member_to_account_entry;sequence_not_causation"
                ),
            }
        )
    return pd.DataFrame(rows)


def _descriptive_profile(
    *,
    family_count: int,
    cross_account_observations: int,
    originator_signal: float,
    receiver_signal: float,
) -> str:
    if family_count < 2 or cross_account_observations < 2:
        return "insufficient_evidence"
    delta = originator_signal - receiver_signal
    if delta >= 0.25:
        return "originator_leaning"
    if delta <= -0.25:
        return "receiver_leaning"
    return "mixed"


def build_account_role_evidence(
    members: pd.DataFrame,
    entries: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    _validate_members(members)
    rows: list[dict[str, Any]] = []

    account_pairs = (
        members[["operator_id", "account_id", "account"]]
        .drop_duplicates()
        .sort_values(["operator_id", "account_id"], na_position="last")
    )

    family_accounts = members.groupby("family_id", dropna=True)["account_id"].nunique().to_dict()

    for _, account_row in account_pairs.iterrows():
        operator_id = _clean(account_row.get("operator_id"))
        account_id = str(account_row["account_id"])
        account = _clean(account_row.get("account"))

        account_members = members.loc[members["account_id"].astype(str).eq(account_id)]
        family_ids = set(account_members["family_id"].astype(str))
        family_count = len(family_ids)
        post_count = int(len(account_members))

        account_entries = entries.loc[entries["account_id"].astype(str).eq(account_id)]
        origin_entries = account_entries.loc[
            account_entries["is_origin_account"].fillna(False).astype(bool)
        ]
        imported_entries = account_entries.loc[
            ~account_entries["is_origin_account"].fillna(False).astype(bool)
        ]

        origin_family_count = int(origin_entries["family_id"].nunique())
        imported_family_count = int(imported_entries["family_id"].nunique())

        cross_account_family_ids = {
            family_id for family_id in family_ids if int(family_accounts.get(family_id, 0)) > 1
        }

        outbound_events = (
            events.loc[events["origin_account_id"].astype(str).eq(account_id)]
            if not events.empty
            else pd.DataFrame()
        )

        inbound_events = (
            events.loc[events["target_account_id"].astype(str).eq(account_id)]
            if not events.empty
            else pd.DataFrame()
        )

        propagated_origin_families = (
            int(outbound_events["family_id"].nunique()) if not outbound_events.empty else 0
        )
        outbound_target_accounts = (
            int(outbound_events["target_account_id"].nunique()) if not outbound_events.empty else 0
        )

        family_origin_rate = float(origin_family_count / family_count) if family_count else 0.0
        imported_family_rate = float(imported_family_count / family_count) if family_count else 0.0
        outbound_propagation_rate = (
            float(propagated_origin_families / origin_family_count) if origin_family_count else 0.0
        )
        cross_account_participation_rate = (
            float(len(cross_account_family_ids) / family_count) if family_count else 0.0
        )

        # Role inference must be conditioned on families that actually crossed
        # accounts. Singleton/one-account families dominate the warehouse and
        # otherwise make every account look like an originator.
        cross_account_flow_observations = propagated_origin_families + imported_family_count
        cross_account_origin_rate = (
            float(propagated_origin_families / cross_account_flow_observations)
            if cross_account_flow_observations
            else 0.0
        )
        cross_account_import_rate = (
            float(imported_family_count / cross_account_flow_observations)
            if cross_account_flow_observations
            else 0.0
        )

        originator_signal = cross_account_origin_rate
        receiver_signal = cross_account_import_rate

        inbound_outperform = (
            [
                bool(value)
                for value in inbound_events["target_outperformed_origin"]
                if value is not None and not pd.isna(value)
            ]
            if not inbound_events.empty
            else []
        )
        imported_repeat = [
            int(value) > 1
            for value in imported_entries["posts_in_family_on_account"]
            if value is not None and not pd.isna(value)
        ]
        outperform_rate = _rate(inbound_outperform)
        repeat_rate = _rate(imported_repeat)
        amplifier_parts = [value for value in (outperform_rate, repeat_rate) if value is not None]
        amplifier_signal = _mean(amplifier_parts)

        import_delays = [
            value
            for value in (_float(item) for item in imported_entries["days_since_family_origin"])
            if value is not None
        ]
        outbound_delays = [
            value
            for value in (
                _float(item) for item in outbound_events.get("delay_from_family_origin_days", [])
            )
            if value is not None
        ]

        cross_account_observations = cross_account_flow_observations
        profile = _descriptive_profile(
            family_count=cross_account_flow_observations,
            cross_account_observations=cross_account_observations,
            originator_signal=originator_signal,
            receiver_signal=receiver_signal,
        )

        rows.append(
            {
                "analytics_schema_version": ANALYTICS_SCHEMA_VERSION,
                "propagation_schema_version": PROPAGATION_SCHEMA_VERSION,
                "operator_id": operator_id,
                "account_id": account_id,
                "account": account,
                "posts": post_count,
                "families_participated": family_count,
                "origin_families": origin_family_count,
                "imported_families": imported_family_count,
                "cross_account_families_participated": len(cross_account_family_ids),
                "propagated_origin_families": propagated_origin_families,
                "outbound_target_accounts": outbound_target_accounts,
                "family_origin_rate": family_origin_rate,
                "imported_family_rate": imported_family_rate,
                "outbound_propagation_rate": outbound_propagation_rate,
                "cross_account_participation_rate": cross_account_participation_rate,
                "cross_account_flow_observations": cross_account_flow_observations,
                "cross_account_origin_rate": cross_account_origin_rate,
                "cross_account_import_rate": cross_account_import_rate,
                "median_import_delay_days": _median(import_delays),
                "median_outbound_delay_days": _median(outbound_delays),
                "imported_family_repeat_rate": repeat_rate,
                "imported_first_post_outperform_origin_rate": outperform_rate,
                "originator_signal": originator_signal,
                "receiver_signal": receiver_signal,
                "amplifier_signal": amplifier_signal,
                "descriptive_profile": profile,
                "evidence_strength": (
                    "high"
                    if cross_account_observations >= 10
                    else "medium"
                    if cross_account_observations >= 3
                    else "low"
                ),
                "notes": (
                    "role signals are conditioned on observed cross-account family flow; "
                    "descriptive evidence only, not a final testing/scaling/conversion role"
                ),
            }
        )

    return pd.DataFrame(rows)


def build_propagation_tables(
    members: pd.DataFrame,
    analysis: pd.DataFrame | None = None,
    performance: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    entries = build_family_account_entries(members, performance)
    events = build_cross_account_propagation(members, analysis, performance)
    return {
        "family_account_entries": entries,
        "cross_account_propagation": events,
        "account_propagation_edges": build_account_propagation_edges(events),
        "account_sequence_edges": build_account_sequence_edges(events),
        "account_role_evidence": build_account_role_evidence(
            members,
            entries,
            events,
        ),
    }
