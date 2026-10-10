"""Read-only creative mechanics and hypothesis verification on canonical TikTok evidence.

Candidate generation and creative interpretation belong to the host AI; this script
computes descriptive evidence without running models, altering warehouse schemas or
silently sampling the first N posts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

MASTER = "data/05_master/"
ANALYTICS = "data/06_analytics/"
MAX_TABLE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ROWS = 1_000_000
AXES = (
    "hook_technique",
    "content_format",
    "dominant_visual_type",
    "pacing",
    "cta_type",
    "hook_psychological_trigger",
    "narrative_structure",
    "attention_mechanisms",
)
FILTER_AXES = (*AXES, "topic", "content_angle", "audience_segment", "video_format")
METRICS = (
    "views_vs_account_median",
    "views_percentile_account",
    "save_rate_by_view",
    "share_rate_by_view",
    "views",
    "saves",
    "shares",
)
DEFAULT_AXES = "hook_technique,content_format,cta_type"


class ResearchError(ValueError):
    """A missing, contradictory or unsafe research input."""


class Sources:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ResearchError("--root must be an existing workspace directory")
        self.bytes_read = 0
        self.paths: list[str] = []

    def read(self, relative: str) -> pd.DataFrame:
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root) or "operating_state" in target.parts:
            raise ResearchError("Evidence path escaped the workspace or touched private state")
        if not target.is_file() or target.suffix != ".parquet":
            raise ResearchError(f"Missing canonical evidence: {relative}; run offline stages first")
        size = target.stat().st_size
        if size > MAX_TABLE_BYTES or self.bytes_read + size > MAX_TOTAL_BYTES:
            raise ResearchError("Evidence exceeds the 256 MiB/table or 512 MiB/query budget")
        self.bytes_read += size
        frame = pd.read_parquet(target)
        if len(frame) > MAX_ROWS:
            raise ResearchError("Source exceeds 1,000,000 rows; partition it before research")
        self.paths.append(relative)
        return frame


def require_unique(frame: pd.DataFrame, key: str, label: str) -> None:
    if key not in frame or frame[key].isna().any() or frame[key].duplicated().any():
        raise ResearchError(f"{label}: {key} missing, null or duplicated")


def text(value: Any, limit: int = 160) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = json.dumps(value, ensure_ascii=False)
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    raw = re.sub(r"\s+", " ", str(value)).strip()
    return raw[:limit] if raw else None


def axis_label(value: Any, axis: str) -> str | None:
    raw = text(value, 500)
    if raw is None or raw.lower() in {"none", "nan", "uncertain", "unknown"}:
        return None
    if axis in {"narrative_structure", "attention_mechanisms"}:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            items = [re.sub(r"\s+", " ", str(v)).strip().casefold() for v in parsed]
            items = [v for v in items if v and v not in {"unknown", "uncertain"}]
            if not items:
                return None
            if axis == "attention_mechanisms":
                items = sorted(set(items))
            raw = " → ".join(items) if axis == "narrative_structure" else " + ".join(items)
    return raw.casefold()[:160]


def number(values: pd.Series) -> pd.Series:
    raw = pd.to_numeric(values, errors="coerce").astype("float64")
    return raw.where(raw.map(math.isfinite))


def stats(frame: pd.DataFrame, metric: str, *, examples: int = 2) -> dict[str, Any]:
    valid = frame.loc[frame["__metric"].notna()].copy()
    values = valid["__metric"]
    answer: dict[str, Any] = {
        "posts": int(len(frame)),
        "observed": int(len(valid)),
        "missing": int(len(frame) - len(valid)),
        "median": float(values.median()) if not valid.empty else None,
        "p25": float(values.quantile(0.25)) if not valid.empty else None,
        "p75": float(values.quantile(0.75)) if not valid.empty else None,
        "distinct_accounts": int(frame["account_id"].nunique(dropna=True)),
    }
    for name, ascending in (("highest", False), ("lowest", True)):
        top = valid.sort_values(
            ["__metric", "post_uid"], ascending=[ascending, True], kind="mergesort"
        ).head(examples)
        answer[name] = [
            {
                "post_uid": str(v["post_uid"]),
                "account_id": text(v["account_id"], 100),
                "metric": float(v["__metric"]),
            }
            for v in top.to_dict("records")
        ]
    return answer


def corpus(args: argparse.Namespace, source: Sources) -> pd.DataFrame:
    performance = source.read(ANALYTICS + "post_performance.parquet")
    analysis = source.read(MASTER + "creative_analysis.parquet")
    require_unique(performance, "post_uid", "post_performance")
    require_unique(analysis, "post_uid", "creative_analysis")
    if args.metric not in performance:
        raise ResearchError(f"Missing performance metric: {args.metric}")
    needed = [field for field in (*FILTER_AXES, "topic") if field in analysis]
    needed = list(dict.fromkeys(needed))
    if "post_uid" not in performance:
        raise ResearchError("Missing canonical post_uid")
    work = performance.merge(
        analysis[["post_uid", *needed]], on="post_uid", how="left", validate="one_to_one"
    )
    if args.content_type != "all":
        work = work.loc[work["content_type"].astype(str).eq(args.content_type)]
    for key in ("operator_id", "account_id"):
        selected = getattr(args, key, None)
        if selected is not None:
            if key not in work:
                raise ResearchError(f"Scope key absent: {key}")
            work = work.loc[work[key].astype("string").eq(selected).fillna(False)]
    work = work.copy()
    work["__metric"] = number(work[args.metric])
    return work


def axes_from(raw: str) -> list[str]:
    axes = [a.strip() for a in raw.split(",")]
    if not 2 <= len(axes) <= 3 or len(set(axes)) != len(axes):
        raise ResearchError("--axes requires two or three distinct creative dimensions")
    if any(axis not in AXES for axis in axes):
        raise ResearchError("Unsupported mechanic axis; use supported Vision fields")
    return axes


def mechanic_id(axes: list[str], labels: tuple[str, ...]) -> str:
    payload = json.dumps(
        list(zip(axes, labels, strict=True)), ensure_ascii=False, separators=(",", ":")
    )
    return "MECH-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def mechanic_corpus(
    args: argparse.Namespace, source: Sources
) -> tuple[pd.DataFrame, list[str], int]:
    axes = axes_from(args.axes)
    work = corpus(args, source)
    for axis in axes:
        if axis not in work:
            raise ResearchError(f"Vision field unavailable: {axis}")
        work["__" + axis] = work[axis].map(lambda value, key=axis: axis_label(value, key))
    before = len(work)
    work = work.dropna(subset=["__" + axis for axis in axes]).copy()
    work["__mechanic_id"] = [
        mechanic_id(axes, tuple(row))
        for row in work[["__" + axis for axis in axes]].itertuples(index=False, name=None)
    ]
    return work, axes, before - len(work)


def mechanic_groups(args: argparse.Namespace, source: Sources) -> dict[str, Any]:
    work, axes, unknown = mechanic_corpus(args, source)
    sizes = work["__mechanic_id"].value_counts()
    qualified = sizes.loc[sizes.ge(args.min_posts)]
    result: list[dict[str, Any]] = []
    for ident in qualified.head(args.max_groups).index:
        group = work.loc[work["__mechanic_id"].eq(ident)]
        signature = {axis: str(group["__" + axis].iloc[0]) for axis in axes}
        row = stats(group, args.metric, examples=args.examples)
        row.update(
            mechanic_id=ident,
            signature=signature,
            distinct_topics=int(group["topic"].nunique(dropna=True)) if "topic" in group else None,
        )
        result.append(row)
    return {
        "command": "mechanic-groups",
        "axes": axes,
        "metric": args.metric,
        "content_type": args.content_type,
        "population_posts": len(work) + unknown,
        "missing_signature_posts": unknown,
        "eligible_posts": len(work),
        "candidate_groups": len(qualified),
        "groups_omitted": max(0, len(qualified) - len(result)),
        "groups": result,
        "all_rows_considered": True,
        "sources": source.paths,
        "interpretation": "Exact Vision-label signatures are candidate mechanics, not proven identity, intent or performance causes.",
    }


def trace_mechanic(args: argparse.Namespace, source: Sources) -> dict[str, Any]:
    work, axes, unknown = mechanic_corpus(args, source)
    group = work.loc[work["__mechanic_id"].eq(args.mechanic_id)].copy()
    if group.empty:
        raise ResearchError("Mechanic ID absent from this scope/axes; rerun mechanic-groups")
    group = group.sort_values(["post_uid"], kind="mergesort")
    page = group.iloc[args.offset : args.offset + args.limit]
    sequence_lookup: dict[str, list[dict[str, Any]]] = {}
    if args.beats:
        seq = source.read(MASTER + "creative_sequence.parquet")
        if "post_uid" not in seq:
            raise ResearchError("Sequence evidence missing post_uid")
        seq = seq.loc[seq["post_uid"].astype(str).isin(page["post_uid"].astype(str))]
        if "position" in seq:
            seq = seq.sort_values(["post_uid", "position"], kind="mergesort")
        for uid, subset in seq.groupby("post_uid", sort=False):
            sequence_lookup[str(uid)] = [
                {
                    field: text(record.get(field), 160)
                    for field in (
                        "position",
                        "role",
                        "start_second",
                        "end_second",
                        "overlay_text",
                        "spoken_summary",
                        "visual_type",
                    )
                }
                for record in subset.head(args.beats).to_dict("records")
            ]
    rows = []
    for record in page.to_dict("records"):
        uid = str(record["post_uid"])
        rows.append(
            {
                "post_uid": uid,
                "account_id": text(record.get("account_id")),
                "created_at": text(record.get("created_at"), 60),
                "topic": text(record.get("topic")),
                "axes": {key: text(record.get(key)) for key in AXES if key in record},
                "metric": float(record["__metric"]) if pd.notna(record["__metric"]) else None,
                "sequence_beats": sequence_lookup.get(uid, []),
                "beats_truncated": bool(args.beats),
            }
        )
    summary = stats(group, args.metric)
    return {
        "command": "trace-mechanic",
        "mechanic_id": args.mechanic_id,
        "signature": {axis: str(group["__" + axis].iloc[0]) for axis in axes},
        "population_posts": len(work) + unknown,
        "total_matching_members": len(group),
        "all_members_aggregated": True,
        "summary": summary,
        "page": {
            "offset": args.offset,
            "limit": args.limit,
            "returned": len(rows),
            "next_offset": args.offset + args.limit
            if args.offset + args.limit < len(group)
            else None,
        },
        "members": rows,
        "sources": source.paths,
        "interpretation": "Labels derive from Vision; shared execution is not proof of a shared core concept.",
    }


def verify_pattern(args: argparse.Namespace, source: Sources) -> dict[str, Any]:
    if not 1 <= len(args.when) <= 3:
        raise ResearchError("Provide one to three --when axis=value conditions")
    work = corpus(args, source)
    mask = pd.Series(True, index=work.index)
    predicates: list[dict[str, str]] = []
    for raw in args.when:
        if len(raw) > 350 or "=" not in raw:
            raise ResearchError("--when must be axis=value, within 350 characters")
        key, value = raw.split("=", 1)
        if key not in FILTER_AXES or not value.strip() or len(value) > 200:
            raise ResearchError("Unsupported pattern axis/value")
        if key not in work:
            raise ResearchError(f"Vision field unavailable: {key}")
        normalized = axis_label(value, key)
        if normalized is None:
            raise ResearchError("Unknown/uncertain labels are not pattern evidence")
        mask &= (
            work[key]
            .map(lambda item, axis=key: axis_label(item, axis))
            .eq(normalized)
            .fillna(False)
        )
        predicates.append({"axis": key, "value": normalized})
    target = work.loc[mask]
    control = work.loc[~mask]
    target_stats = stats(target, args.metric)
    control_stats = stats(control, args.metric)
    target_observed = target_stats["observed"]
    control_observed = control_stats["observed"]
    comparison = (
        target_stats["median"] - control_stats["median"]
        if target_stats["median"] is not None and control_stats["median"] is not None
        else None
    )
    both_sufficient = target_observed >= args.min_posts and control_observed >= args.min_posts
    accounts = []
    for account_id, subset in work.groupby("account_id", dropna=True, sort=True):
        found = subset.loc[mask.loc[subset.index]]
        others = subset.loc[~mask.loc[subset.index]]
        accounts.append(
            {
                "account_id": text(account_id, 100),
                "target_posts": len(found),
                "control_posts": len(others),
                "target_median": stats(found, args.metric, examples=0)["median"],
                "control_median": stats(others, args.metric, examples=0)["median"],
            }
        )
    accounts.sort(key=lambda item: (-item["target_posts"], str(item["account_id"])))
    return {
        "command": "verify-pattern",
        "predicates": predicates,
        "scope": {
            "operator_id": args.operator_id,
            "account_id": args.account_id,
            "content_type": args.content_type,
        },
        "metric": args.metric,
        "population_posts": len(work),
        "target": target_stats,
        "comparison": control_stats,
        "median_difference": comparison,
        "per_account": accounts[: args.max_accounts],
        "accounts_omitted": max(0, len(accounts) - args.max_accounts),
        "disposition": "descriptive_association_only"
        if both_sufficient
        else "insufficient_evidence",
        "full_population_evaluated": True,
        "exploratory_multiple_testing_warning": True,
        "sources": source.paths,
        "interpretation": "Not a causal test; compare on independent holdout evidence and assess account/topic/time confounding.",
    }


def trace_strategy(args: argparse.Namespace, source: Sources) -> dict[str, Any]:
    hypotheses = source.read(ANALYTICS + "strategy_hypotheses.parquet")
    require_unique(hypotheses, "hypothesis_id", "strategy_hypotheses")
    row = hypotheses.loc[hypotheses["hypothesis_id"].astype(str).eq(args.hypothesis_id)]
    if row.empty:
        raise ResearchError("Hypothesis ID absent from deterministic baseline")
    links = source.read(ANALYTICS + "strategy_pattern_links.parquet")
    evidence = source.read(ANALYTICS + "strategy_evidence_links.parquet")
    patterns = source.read(ANALYTICS + "patterns.parquet")
    require_unique(patterns, "pattern_id", "patterns")
    for table, key in ((links, "hypothesis_id"), (evidence, "hypothesis_id")):
        if key not in table:
            raise ResearchError(f"Missing {key} in strategy lineage")
    matched_links = links.loc[links["hypothesis_id"].astype(str).eq(args.hypothesis_id)]
    if "pattern_id" not in matched_links:
        raise ResearchError("Missing pattern_id in strategy links")
    linked = matched_links.merge(
        patterns[
            [
                "pattern_id",
                *[
                    k
                    for k in (
                        "pattern_type",
                        "title",
                        "observation",
                        "sample_size",
                        "evidence_strength",
                        "counter_evidence_json",
                    )
                    if k in patterns
                ],
            ]
        ],
        on="pattern_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if (linked["_merge"] == "left_only").any():
        raise ResearchError("Strategy references missing pattern rows")
    matched = evidence.loc[evidence["hypothesis_id"].astype(str).eq(args.hypothesis_id)]
    ordered = matched.sort_values(
        [
            k
            for k in ("relation", "pattern_id", "post_uid", "family_id", "account_id")
            if k in matched
        ],
        na_position="last",
        kind="mergesort",
    )
    excerpt = ordered.iloc[args.offset : args.offset + args.limit]
    headers = (
        "hypothesis_id",
        "hypothesis_type",
        "title",
        "claim",
        "confidence_score",
        "confidence_band",
        "supporting_patterns_count",
        "counter_patterns_count",
        "alternative_explanations_json",
        "causal_claim",
    )
    return {
        "command": "trace-strategy",
        "hypothesis": {k: text(row.iloc[0][k], 500) for k in headers if k in row},
        "total_pattern_links": len(linked),
        "pattern_links": [
            {
                k: text(rec.get(k), 250)
                for k in (
                    "pattern_id",
                    "relation",
                    "pattern_type",
                    "title",
                    "observation",
                    "sample_size",
                    "evidence_strength",
                    "counter_evidence_json",
                )
                if k in rec
            }
            for rec in linked.head(args.max_patterns).to_dict("records")
        ],
        "patterns_omitted": max(0, len(linked) - args.max_patterns),
        "total_evidence_links": len(ordered),
        "page": {
            "offset": args.offset,
            "limit": args.limit,
            "returned": len(excerpt),
            "next_offset": args.offset + args.limit
            if args.offset + args.limit < len(ordered)
            else None,
        },
        "evidence": [
            {
                k: text(record.get(k), 160)
                for k in (
                    "post_uid",
                    "family_id",
                    "account_id",
                    "pattern_id",
                    "relation",
                    "link_role",
                )
                if k in record
            }
            for record in excerpt.to_dict("records")
        ],
        "sources": source.paths,
        "interpretation": "Deterministic hypothesis confidence is not a calibrated probability or proof of intent.",
    }


def bounded(low: int, high: int) -> Any:
    def parse(raw: str) -> int:
        value = int(raw)
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"Expected integer {low}..{high}")
        return value

    return parse


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("mechanic-groups", "trace-mechanic", "verify-pattern"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--metric", choices=METRICS, default="views_vs_account_median")
        command.add_argument("--content-type", choices=("all", "slideshow", "video"), default="all")
        command.add_argument("--operator-id")
        command.add_argument("--account-id")
        if name in ("mechanic-groups", "trace-mechanic"):
            command.add_argument("--axes", default=DEFAULT_AXES)
        if name == "mechanic-groups":
            command.add_argument("--min-posts", type=bounded(2, 10000), default=3)
            command.add_argument("--max-groups", type=bounded(1, 30), default=12)
            command.add_argument("--examples", type=bounded(0, 3), default=2)
        elif name == "trace-mechanic":
            command.add_argument("--mechanic-id", required=True)
            command.add_argument("--offset", type=bounded(0, 1000000), default=0)
            command.add_argument("--limit", type=bounded(1, 50), default=15)
            command.add_argument("--beats", type=bounded(0, 5), default=2)
        else:
            command.add_argument("--when", action="append", required=True)
            command.add_argument("--min-posts", type=bounded(3, 10000), default=5)
            command.add_argument("--max-accounts", type=bounded(1, 30), default=12)
    strategy = sub.add_parser("trace-strategy", allow_abbrev=False)
    strategy.add_argument("--hypothesis-id", required=True)
    strategy.add_argument("--offset", type=bounded(0, 1000000), default=0)
    strategy.add_argument("--limit", type=bounded(1, 50), default=20)
    strategy.add_argument("--max-patterns", type=bounded(1, 30), default=15)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        source = Sources(Path(args.root).expanduser())
        if args.command == "mechanic-groups":
            result = mechanic_groups(args, source)
        elif args.command == "trace-mechanic":
            if not re.fullmatch(r"MECH-[A-F0-9]{16}", args.mechanic_id):
                raise ResearchError("Invalid mechanic_id; use the ID from mechanic-groups")
            result = trace_mechanic(args, source)
        elif args.command == "verify-pattern":
            result = verify_pattern(args, source)
        else:
            if not re.fullmatch(r"[A-Za-z0-9_:.~-]{1,200}", args.hypothesis_id):
                raise ResearchError("Invalid hypothesis_id")
            result = trace_strategy(args, source)
        print(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False))
        return 0
    except (ResearchError, OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc), "command": args.command, "untrusted_output": True}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
