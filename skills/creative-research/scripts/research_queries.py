"""Read-only cohort comparisons and full-family tracing for TikTok research.

Runs under the existing offline bridge's isolated Python. Aggregate all eligible rows;
bound the number of returned groups/examples and page member details rather than
silently sampling the first 100 posts. Never modifies source tables.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import date
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

ANALYTICS = "data/06_analytics/"
MASTER = "data/05_master/"
MAX_TABLE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ROWS = 1_000_000

METRICS = (
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "views_percentile_account",
    "views_vs_account_median",
    "views_percentile_operator",
    "views_vs_operator_median",
    "save_rate_by_view",
    "share_rate_by_view",
    "comment_rate_by_view",
    "like_rate_by_view",
)
ANALYSIS_DIMENSIONS = (
    "topic",
    "content_angle",
    "hook_technique",
    "hook_psychological_trigger",
    "content_format",
    "video_format",
    "dominant_visual_type",
    "visual_aesthetic",
    "pacing",
    "cta_type",
)
GROUP_BY = ("account_id", "operator_id", "content_type", "family_id", *ANALYSIS_DIMENSIONS)
FAMILY_DIMENSIONS = (*ANALYSIS_DIMENSIONS, "narrative_structure", "attention_mechanisms")


class ResearchError(ValueError):
    """Missing, inconsistent or unsafe source/query input."""


def bounded(low: int, high: int) -> Any:
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Expected integer") from exc
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"Must be between {low} and {high}")
        return value

    return parse


def scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        return (
            (int(value) if float(value).is_integer() else float(value))
            if math.isfinite(float(value))
            else None
        )
    if isinstance(value, (str, bool)):
        return value
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def label(value: Any) -> str:
    value = scalar(value)
    return str(value).strip() if value is not None and str(value).strip() else "unknown"


def short(value: Any, limit: int = 240) -> Any:
    value = scalar(value)
    return (
        value[:limit] + "… [truncated]" if isinstance(value, str) and len(value) > limit else value
    )


class SourceTables:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.bytes_read = 0
        self.sources: list[str] = []

    def load(self, relative: str) -> pd.DataFrame:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ResearchError(f"Unsafe source path: {relative}")
        if not path.is_file():
            raise ResearchError(
                f"Missing required source table: {relative}; build offline stages first"
            )
        size = path.stat().st_size
        if size > MAX_TABLE_BYTES or self.bytes_read + size > MAX_TOTAL_BYTES:
            raise ResearchError("Evidence exceeds 256 MiB/table or 512 MiB/query budget")
        self.bytes_read += size
        work = pd.read_parquet(path)
        if len(work) > MAX_ROWS:
            raise ResearchError("Source table exceeds 1,000,000 rows; use scoped materialization")
        self.sources.append(relative)
        return work


def unique(frame: pd.DataFrame, keys: list[str], source: str) -> None:
    missing = sorted(set(keys) - set(frame.columns))
    if missing:
        raise ResearchError(f"{source} missing required columns: {', '.join(missing)}")
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ResearchError(f"{source} has missing/duplicate IDs: {', '.join(keys)}")


def parse_day(raw: str, name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ResearchError(f"{name} must be YYYY-MM-DD (UTC publication date)") from exc


def apply_scope(frame: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    scoped = frame
    for key in ("operator_id", "account_id"):
        value = getattr(args, key, None)
        if value is not None:
            if key not in scoped:
                raise ResearchError(f"Cannot scope without {key}")
            scoped = scoped.loc[scoped[key].astype("string").eq(value).fillna(False)]
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    if since or until:
        if "created_at" not in scoped:
            raise ResearchError("Publication date missing from performance")
        dates = pd.to_datetime(scoped["created_at"], errors="coerce", utc=True).dt.date
        if since:
            scoped = scoped.loc[dates.ge(parse_day(since, "--since")).fillna(False)]
            dates = dates.loc[scoped.index]
        if until:
            scoped = scoped.loc[dates.le(parse_day(until, "--until")).fillna(False)]
    return scoped.copy()


def numeric(values: pd.Series) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce").astype("float64")
    return result.where(result.map(math.isfinite))


def median(values: pd.Series) -> float | None:
    return float(values.median()) if not values.empty else None


def evidence_examples(
    frame: pd.DataFrame, metric: str, count: int, ascending: bool
) -> list[dict[str, Any]]:
    if count == 0:
        return []
    sample = (
        frame.loc[frame[metric].notna()]
        .sort_values([metric, "post_uid"], ascending=[ascending, True], kind="mergesort")
        .head(count)
    )
    return [
        {
            "post_uid": str(row["post_uid"]),
            "account_id": short(row.get("account_id"), 100),
            "metric": float(row[metric]),
        }
        for row in sample.to_dict("records")
    ]


def compare_cohorts(args: argparse.Namespace, source: SourceTables) -> dict[str, Any]:
    perf = source.load(ANALYTICS + "post_performance.parquet")
    unique(perf, ["post_uid"], "post_performance")
    if args.metric not in perf:
        raise ResearchError(f"Metric {args.metric} absent from post_performance")
    scoped = apply_scope(perf, args)
    if args.group_by == "family_id" or args.family_id is not None:
        members = source.load(ANALYTICS + "creative_family_members.parquet")
        unique(members, ["post_uid"], "creative_family_members")
        if "family_id" not in members:
            raise ResearchError("creative_family_members missing family_id")
        scoped = scoped.merge(
            members[["post_uid", "family_id"]], on="post_uid", how="left", validate="one_to_one"
        )
        if args.family_id is not None:
            scoped = scoped.loc[
                scoped["family_id"].astype("string").eq(args.family_id).fillna(False)
            ]
    if args.group_by in ANALYSIS_DIMENSIONS:
        analysis = source.load(MASTER + "creative_analysis.parquet")
        unique(analysis, ["post_uid"], "creative_analysis")
        if args.group_by not in analysis:
            raise ResearchError(f"creative_analysis missing {args.group_by}")
        scoped = scoped.merge(
            analysis[["post_uid", args.group_by]], on="post_uid", how="left", validate="one_to_one"
        )
    if args.group_by not in scoped:
        raise ResearchError(f"Unknown group field {args.group_by}")
    scoped["__group"] = scoped[args.group_by].map(label)
    scoped["__metric"] = numeric(scoped[args.metric])
    requested = {part.strip() for part in args.values.split(",")} if args.values else None
    if requested is not None and (not all(requested) or any(len(v) > 200 for v in requested)):
        raise ResearchError("--values requires nonempty comma-separated labels <=200 chars")
    cohort = scoped.loc[scoped["__group"].isin(requested)] if requested is not None else scoped
    counts = cohort["__group"].value_counts(dropna=False)
    selected_names = counts.head(args.max_groups).index.tolist()
    groups: list[dict[str, Any]] = []
    for group_name, group in cohort.loc[cohort["__group"].isin(selected_names)].groupby(
        "__group", sort=False
    ):
        observed = group.loc[group["__metric"].notna()].copy()
        observed[args.metric] = observed["__metric"]
        values = observed["__metric"]
        groups.append(
            {
                "value": short(group_name, 200),
                "posts": int(len(group)),
                "observed": len(values),
                "missing_metric": int(len(group) - len(values)),
                "median": median(values),
                "p25": float(values.quantile(0.25)) if not values.empty else None,
                "p75": float(values.quantile(0.75)) if not values.empty else None,
                "distinct_accounts": int(group["account_id"].nunique(dropna=True)),
                "small_sample": len(values) < 5,
                "highest": evidence_examples(observed, args.metric, args.examples, False),
                "lowest": evidence_examples(observed, args.metric, args.examples, True),
            }
        )
    groups.sort(key=lambda row: (-row["posts"], str(row["value"])))
    return {
        "command": "compare-cohorts",
        "group_by": args.group_by,
        "metric": args.metric,
        "scope": {
            "operator_id": args.operator_id,
            "account_id": args.account_id,
            "family_id": args.family_id,
            "since_utc": args.since,
            "until_utc": args.until,
        },
        "population_posts": len(scoped),
        "population_metric_observed": int(scoped["__metric"].notna().sum()),
        "population_median": median(scoped["__metric"].dropna()),
        "cohort_posts": len(cohort),
        "cohort_groups": int(len(counts)),
        "groups_omitted": int(len(counts) - len(groups)),
        "requested_values_missing": sorted(requested - set(scoped["__group"]))
        if requested is not None
        else [],
        "groups": groups,
        "all_eligible_rows_aggregated": True,
        "examples_are_bounded": True,
        "sources": source.sources,
        "interpretation": "Descriptive association only; small/overlapping cohorts cannot prove creative causality.",
    }


def frequency(values: pd.Series, max_values: int = 8) -> dict[str, Any]:
    counts = Counter(values.map(label))
    top = sorted(counts.items(), key=lambda row: (-row[1], row[0]))[:max_values]
    return {
        "observed": int(len(values) - counts.get("unknown", 0)),
        "unknown": int(counts.get("unknown", 0)),
        "values": [{"value": short(k, 200), "posts": int(n)} for k, n in top],
        "categories_omitted": max(0, len(counts) - len(top)),
    }


def trace_family(args: argparse.Namespace, source: SourceTables) -> dict[str, Any]:
    families = source.load(ANALYTICS + "creative_families.parquet")
    members = source.load(ANALYTICS + "creative_family_members.parquet")
    unique(families, ["family_id"], "creative_families")
    unique(members, ["post_uid"], "creative_family_members")
    if "family_id" not in members:
        raise ResearchError("creative_family_members missing family_id")
    selected = families.loc[families["family_id"].astype("string").eq(args.family_id).fillna(False)]
    if selected.empty:
        raise ResearchError(f"Unknown family_id: {args.family_id}")
    # Members can have cached topic, percentile etc. Use canonical analysis/performance
    # for those fields; otherwise overlapping merge columns would silently shadow them.
    keys = (
        "family_id",
        "post_uid",
        "operator_id",
        "account_id",
        "created_at",
        "family_member_index",
        "match_score_to_origin",
    )
    member_fields = [key for key in keys if key in members]
    rows = members.loc[
        members["family_id"].astype("string").eq(args.family_id).fillna(False), member_fields
    ].copy()
    if args.operator_id is not None:
        if "operator_id" not in rows:
            raise ResearchError("creative_family_members missing operator_id")
        rows = rows.loc[rows["operator_id"].astype("string").eq(args.operator_id).fillna(False)]
    if rows.empty:
        raise ResearchError(f"No matching family members: {args.family_id} in requested scope")
    analysis = source.load(MASTER + "creative_analysis.parquet")
    perf = source.load(ANALYTICS + "post_performance.parquet")
    unique(analysis, ["post_uid"], "creative_analysis")
    unique(perf, ["post_uid"], "post_performance")
    dimensions = [key for key in FAMILY_DIMENSIONS if key in analysis]
    joined = rows.merge(
        analysis[["post_uid", *dimensions]],
        on="post_uid",
        how="left",
        validate="one_to_one",
        indicator="_analysis_match",
    )
    metrics = [
        key
        for key in (
            "views",
            "views_vs_account_median",
            "views_percentile_account",
            "save_rate_by_view",
        )
        if key in perf
    ]
    joined = joined.merge(
        perf[["post_uid", *metrics]],
        on="post_uid",
        how="left",
        validate="one_to_one",
        indicator="_perf_match",
    )
    sort_cols = (
        ["family_member_index", "post_uid"] if "family_member_index" in joined else ["post_uid"]
    )

    joined = joined.sort_values(sort_cols, kind="mergesort")
    start, end = args.offset, args.offset + args.limit
    page = joined.iloc[start:end]
    sequence_by_post: dict[str, list[dict[str, Any]]] = {}
    if args.beats:
        sequence = source.load(MASTER + "creative_sequence.parquet")
        if "post_uid" not in sequence:
            raise ResearchError("creative_sequence missing post_uid")
        current = sequence.loc[
            sequence["post_uid"].astype("string").isin(page["post_uid"].astype(str))
        ]
        if "position" in current:
            current = current.sort_values(["post_uid", "position"], kind="mergesort")
        fields = (
            "position",
            "role",
            "start_second",
            "end_second",
            "visual_type",
            "overlay_text",
            "spoken_summary",
        )
        for uid, group in current.groupby("post_uid", sort=False):
            sequence_by_post[str(uid)] = [
                {key: short(record[key], 160) for key in fields if key in record}
                for record in group.to_dict("records")
            ]
    page_rows = []
    for record in page.to_dict("records"):
        uid = str(record["post_uid"])
        beats = sequence_by_post.get(uid, [])
        page_rows.append(
            {
                "post_uid": uid,
                "account_id": short(record.get("account_id"), 100),
                "created_at": short(record.get("created_at"), 50),
                "match_score_to_origin": scalar(record.get("match_score_to_origin")),
                "evidence": {key: short(record.get(key)) for key in dimensions},
                "performance": {key: scalar(record.get(key)) for key in metrics},
                "sequence_total": len(beats) if args.beats else None,
                "sequence_beats": beats[: args.beats],
                "sequence_beats_omitted": max(0, len(beats) - args.beats) if args.beats else None,
            }
        )
    head_fields = (
        "family_id",
        "operator_id",
        "family_origin_post_uid",
        "representative_post_uid",
        "first_seen",
        "last_seen",
        "member_count",
        "family_model",
        "family_confidence",
        "core_topic",
        "core_hook_formula",
        "core_creative_formula",
    )
    head = {key: short(selected.iloc[0][key], 150) for key in head_fields if key in selected}
    relative = (
        numeric(joined["views_vs_account_median"]) if "views_vs_account_median" in joined else None
    )
    return {
        "command": "trace-family",
        "family": head,
        "total_matching_members": len(joined),
        "source_rows_missing": {
            "creative_analysis": int((joined["_analysis_match"] == "left_only").sum()),
            "post_performance": int((joined["_perf_match"] == "left_only").sum()),
        },
        "all_members_aggregated": True,
        "dimensions": {key: frequency(joined[key]) for key in dimensions},
        "views_vs_account_median": {
            "observed": int(relative.notna().sum()),
            "median": median(relative.dropna()),
        }
        if relative is not None
        else None,
        "page": {
            "offset": start,
            "limit": args.limit,
            "returned": len(page_rows),
            "next_offset": end if end < len(joined) else None,
        },
        "members": page_rows,
        "sources": source.sources,
        "interpretation": "Similarity-based family membership does not prove shared intent or independent replication.",
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument("--root", required=True)
    commands = p.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare-cohorts", allow_abbrev=False)
    compare.add_argument("--group-by", choices=GROUP_BY, required=True)
    compare.add_argument("--metric", choices=METRICS, default="views_vs_account_median")
    for key in ("operator-id", "account-id", "family-id", "since", "until", "values"):
        compare.add_argument("--" + key)
    compare.add_argument("--max-groups", type=bounded(1, 30), default=10)
    compare.add_argument("--examples", type=bounded(0, 3), default=2)
    family = commands.add_parser("trace-family", allow_abbrev=False)
    family.add_argument("--family-id", required=True)
    family.add_argument("--operator-id")
    family.add_argument("--offset", type=bounded(0, 1_000_000), default=0)
    family.add_argument("--limit", type=bounded(1, 100), default=20)
    family.add_argument("--beats", type=bounded(0, 10), default=3)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ResearchError("--root must be a workspace directory")
        source = SourceTables(root)
        if args.command == "compare-cohorts":
            result = compare_cohorts(args, source)
        else:
            if not re.fullmatch(r"[A-Za-z0-9_:.~-]{1,200}", args.family_id):
                raise ResearchError("Invalid family_id")
            result = trace_family(args, source)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, default=str))
        return 0
    except (ResearchError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "command": args.command, "untrusted_output": True}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
