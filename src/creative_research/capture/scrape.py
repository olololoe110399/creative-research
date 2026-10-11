"""Archive confirmed public TikTok profiles through the explicit Apify command.

Capture metadata and per-account records with configured sample, timeout and cost
caps. Installation and examples live in docs/.
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError

from creative_research.capture.cache import fingerprint, sha256
from creative_research.capture.normalization import guess_account, normalize_post
from creative_research.errors import ApplicationError
from creative_research.identity import clean_account_handle
from creative_research.infrastructure.config import RuntimeSettings
from creative_research.infrastructure.locking import project_writer
from creative_research.infrastructure.logging import redact
from creative_research.infrastructure.paths import confined_path, resolve_path
from creative_research.infrastructure.storage import (
    atomic_output,
    read_json_object,
    read_jsonl,
)
from creative_research.infrastructure.storage import write_jsonl as storage_write_jsonl
from creative_research.infrastructure.storage import write_text as atomic_write_text

ACTOR = "clockworks/tiktok-profile-scraper"


@dataclass(frozen=True, slots=True)
class ScrapeOptions:
    """CLI-independent parameters for this workflow."""

    accounts_file: str
    out: str
    token: str | None
    batch_size: int
    max_posts: int
    actor_timeout: int
    max_charge_usd: float | None
    comments: int
    top_level_comments: int
    max_replies: int
    oldest_date: str | None
    newest_date: str | None
    preflight: bool
    resume: bool = False
    recover_runs: list[str] | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_accounts(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)

    result: list[str] = []
    seen: set[str] = set()

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        username = clean_account_handle(line)
        key = username.lower()

        if username and key not in seen:
            seen.add(key)
            result.append(username)

    return result


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def to_plain(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain(v) for v in value]

    if hasattr(value, "model_dump"):
        try:
            return to_plain(value.model_dump(by_alias=True))
        except (TypeError, ValueError):
            pass

    if hasattr(value, "__dict__"):
        try:
            return {k: to_plain(v) for k, v in vars(value).items() if not k.startswith("_")}
        except (TypeError, ValueError):
            pass

    return str(value)


def profile_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    author = item.get("authorMeta")
    if not isinstance(author, dict) or not author:
        return None

    return {
        "account": guess_account(item),
        "captured_at": utc_now(),
        "authorMeta": author,
    }


def json_dump(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def overwrite_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    storage_write_jsonl(path, rows)


def write_normalized_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "account",
        "post_id",
        "url",
        "caption",
        "created_at",
        "is_pinned",
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "hashtags",
        "author_id",
        "author_name",
        "author_nickname",
        "followers",
        "following",
        "author_total_likes",
        "author_total_videos",
        "video_duration",
        "video_width",
        "video_height",
        "music_name",
        "music_author",
        "error",
        "error_code",
    ]

    with atomic_output(path) as temporary:
        with temporary.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()

            for row in rows:
                out = dict(row)
                if isinstance(out.get("hashtags"), list):
                    out["hashtags"] = "|".join(str(x) for x in out["hashtags"])
                writer.writerow(out)


def build_actor_input(
    profiles: list[str],
    args: ScrapeOptions,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profiles": profiles,
        "profileScrapeSections": ["videos"],
        "profileSorting": "latest",
        "resultsPerPage": args.max_posts,
        "excludePinnedPosts": False,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars": False,
        "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES",
        "commentsPerPost": args.comments,
        "topLevelCommentsPerPost": args.top_level_comments,
        "maxRepliesPerComment": args.max_replies,
    }

    if args.oldest_date:
        payload["oldestPostDateUnified"] = args.oldest_date

    if args.newest_date:
        payload["newestPostDate"] = args.newest_date

    return payload


def run_actor_batch(
    client: ApifyClient,
    profiles: list[str],
    args: ScrapeOptions,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    actor_input = build_actor_input(profiles, args)

    print()
    print("Starting Apify Actor batch:")
    for p in profiles:
        print(f"  @{p}")

    run = client.actor(ACTOR).start(
        run_input=actor_input,
        run_timeout=timedelta(seconds=args.actor_timeout),
        max_total_charge_usd=Decimal(str(args.max_charge_usd))
        if args.max_charge_usd is not None
        else None,
    )

    if run is None:
        raise RuntimeError("Apify did not return a run object.")

    plain = to_plain(run)
    if not isinstance(plain, dict) or not plain.get("id"):
        raise RuntimeError("Apify did not return a run ID; launch outcome is unknown")
    if checkpoint:
        checkpoint(plain)
    return wait_actor_run(client, str(plain["id"]), args.actor_timeout)


def wait_actor_run(client: ApifyClient, run_id: str, timeout: int) -> dict[str, Any]:
    run = client.run(run_id).wait_for_finish(wait_duration=timedelta(seconds=timeout))
    plain = to_plain(run)
    if not isinstance(plain, dict):
        raise RuntimeError("Apify run is unavailable; retain its ID and resume later")
    return plain


def download_dataset_items(
    client: ApifyClient,
    dataset_id: str,
) -> list[dict[str, Any]]:
    dataset = client.dataset(dataset_id)
    items: list[dict[str, Any]] = []

    for item in dataset.iterate_items(clean=False):
        plain = to_plain(item)
        if isinstance(plain, dict):
            items.append(plain)

    return items


def split_and_write(
    all_items: list[dict[str, Any]],
    out: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profiles: dict[str, dict[str, Any]] = {}
    normalized_rows: list[dict[str, Any]] = []
    seen_post_ids: set[tuple[str, str]] = set()

    for item in all_items:
        if item.get("error") or item.get("errorCode"):
            continue
        account = guess_account(item)
        by_account[account].append(item)

        profile = profile_from_item(item)
        if profile and account != "unknown":
            profiles[account] = profile

        normalized = normalize_post(item)
        key = (normalized["account"].lower(), normalized["post_id"])
        if key not in seen_post_ids:
            seen_post_ids.add(key)
            normalized_rows.append(normalized)

    posts_dir = out / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    post_paths = {account: confined_path(posts_dir, f"{account}.jsonl") for account in by_account}
    profiles_dir = out / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_paths = {
        account: confined_path(profiles_dir, f"{account}.json") for account in profiles
    }
    for account, rows in sorted(by_account.items()):
        overwrite_jsonl(post_paths[account], rows)

    for account, profile in sorted(profiles.items()):
        json_dump(profile, profile_paths[account])

    normalized_rows.sort(
        key=lambda x: (
            str(x.get("account") or "").lower(),
            str(x.get("created_at") or ""),
            str(x.get("post_id") or ""),
        )
    )

    overwrite_jsonl(out / "normalized" / "posts.jsonl", normalized_rows)
    write_normalized_csv(out / "normalized" / "posts.csv", normalized_rows)
    for directory, pattern, current in (
        (posts_dir, "*.jsonl", set(post_paths.values())),
        (profiles_dir, "*.json", set(profile_paths.values())),
    ):
        for path in directory.glob(pattern):
            if path not in current:
                confined_path(directory, path.name).unlink()

    counts = {account: len(rows) for account, rows in sorted(by_account.items())}

    return normalized_rows, counts


def archive_posts(options: ScrapeOptions) -> dict[str, Any]:

    if options.actor_timeout <= 0 or options.max_posts <= 0:
        raise ValueError("--actor-timeout and --max-posts must be positive integers")
    if options.max_charge_usd is not None and (
        not math.isfinite(options.max_charge_usd) or options.max_charge_usd <= 0
    ):
        raise ValueError("--max-charge-usd must be a finite positive amount")

    if options.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if options.comments < 0 or options.top_level_comments < 0 or options.max_replies < 0:
        raise SystemExit("Comment limits cannot be negative.")

    accounts_file = resolve_path(options.accounts_file)
    accounts = read_accounts(accounts_file)
    if not accounts:
        raise ValueError("Accounts file is empty")
    for account in accounts:
        confined_path(resolve_path(options.out) / "posts", f"{account}.jsonl")
    if options.preflight:
        print("Preflight PASS. No Apify token used or provider call made.")
        return {"preflight": True}

    with project_writer():
        return _archive_posts(options, accounts_file, accounts)


def _archive_posts(
    options: ScrapeOptions, accounts_file: Path, accounts: list[str]
) -> dict[str, Any]:

    out = resolve_path(options.out)
    existing = out.exists() and (not out.is_dir() or any(out.iterdir()))
    if existing and not options.resume:
        raise ValueError("Capture output already exists; choose a new snapshot directory")
    token = options.token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit(
            "APIFY_TOKEN is missing.\n\n"
            "macOS/Linux:\n"
            '  export APIFY_TOKEN="apify_api_..."\n\n'
            "PowerShell:\n"
            '  $env:APIFY_TOKEN="apify_api_..."\n'
        )

    run_info: dict[str, Any] = {
        "actor": ACTOR,
        "started_at": utc_now(),
        "accounts_file": str(accounts_file),
        "accounts": accounts,
        "account_count": len(accounts),
        "settings": {
            "batch_size": options.batch_size,
            "max_posts_per_profile": options.max_posts,
            "comments_per_post": options.comments,
            "top_level_comments_per_post": options.top_level_comments,
            "max_replies_per_comment": options.max_replies,
            "oldest_date": options.oldest_date,
            "newest_date": options.newest_date,
            "max_charge_usd_per_batch": options.max_charge_usd,
            "actor_timeout": options.actor_timeout,
        },
        "batches": [],
    }
    config = fingerprint({"actor": ACTOR, "accounts": accounts, "settings": run_info["settings"]})
    if options.resume:
        previous = read_json_object(out / "run_info.json")
        if previous.get("config_fingerprint") != config:
            raise ValueError("Resume requires the same accounts and capture settings")
        run_info = previous
    run_info["config_fingerprint"] = config
    run_info.setdefault("batch_history", [])
    recovery: dict[int, str] = {}
    for value in options.recover_runs or []:
        index, separator, run_id = value.partition("=")
        if not options.resume or not separator or not index.isdigit() or not run_id:
            raise ValueError("--recover-run requires --resume and BATCH=RUN_ID")
        recovery[int(index)] = run_id
    if any(
        index < 1 or index > math.ceil(len(accounts) / options.batch_size) for index in recovery
    ):
        raise ValueError("Recovery batch index is outside the requested batches")
    run_info.pop("finished_at", None)
    run_info.pop("manifest", None)
    json_dump(run_info, out / "run_info.json")
    (out / "raw" / "batches").mkdir(parents=True, exist_ok=True)
    (out / "profiles").mkdir(parents=True, exist_ok=True)
    (out / "posts").mkdir(parents=True, exist_ok=True)
    (out / "normalized").mkdir(parents=True, exist_ok=True)

    atomic_write_text(out / "accounts.txt", "\n".join(accounts) + "\n")

    client = ApifyClient(
        token,
        timeout_medium=timedelta(seconds=RuntimeSettings.from_environ().request_timeout),
        max_retries=0,
    )

    all_items: list[dict[str, Any]] = []
    failed_batches: list[dict[str, Any]] = []
    interrupted = False
    started = time.time()

    for batch_index, batch_profiles in enumerate(
        chunks(accounts, options.batch_size),
        start=1,
    ):
        batch_started = utc_now()
        previous = next(
            (record for record in run_info["batches"] if record["batch_index"] == batch_index), {}
        )
        batch_record = dict(previous) or {
            "batch_index": batch_index,
            "profiles": batch_profiles,
            "started_at": batch_started,
        }
        items_file = out / "raw" / "batches" / f"batch_{batch_index:03d}_items.jsonl"

        def save_record(record: dict[str, Any] = batch_record, index: int = batch_index) -> None:
            run_info["batches"] = [
                previous for previous in run_info["batches"] if previous["batch_index"] != index
            ] + [record]
            run_info["batches"].sort(key=lambda record: record["batch_index"])
            json_dump(record, out / "raw" / "batches" / f"batch_{index:03d}_run.json")
            json_dump(run_info, out / "run_info.json")

        def checkpoint(
            run: dict[str, Any],
            record: dict[str, Any] = batch_record,
            save: Callable[[], None] = save_record,
        ) -> None:
            record.update(
                run=run,
                run_id=run.get("id"),
                status=run.get("status"),
                dataset_id=run.get("defaultDatasetId") or run.get("default_dataset_id"),
                checkpoint="waiting",
            )
            save()

        try:
            if (
                batch_record.get("checkpoint") == "completed"
                and items_file.is_file()
                and batch_record.get("items_sha256") == sha256(items_file)
            ):
                all_items.extend(read_jsonl(items_file))
                continue
            if batch_index in recovery:
                batch_record.update(run_id=recovery[batch_index], checkpoint="waiting", status=None)
                save_record()
            if batch_record.get("run_id") and batch_record.get("status") not in {
                "FAILED",
                "TIMED-OUT",
                "ABORTED",
            }:
                run = wait_actor_run(client, str(batch_record["run_id"]), options.actor_timeout)
            else:
                if batch_record.get("checkpoint") in {"launching", "launch_unknown"}:
                    raise RuntimeError(
                        f"Batch {batch_index} launch outcome is unknown. Find its Apify run ID, "
                        f"then resume with --recover-run {batch_index}=RUN_ID; no new job was started"
                    )
                if previous:
                    run_info["batch_history"].append(previous)
                batch_record.clear()
                batch_record.update(
                    {
                        "batch_index": batch_index,
                        "profiles": batch_profiles,
                        "started_at": batch_started,
                        "checkpoint": "launching",
                    }
                )
                save_record()
                run = run_actor_batch(
                    client=client,
                    profiles=batch_profiles,
                    args=options,
                    checkpoint=checkpoint,
                )
            checkpoint(run)

            status = str(run.get("status") or run.get("statusMessage") or "UNKNOWN")

            if status != "SUCCEEDED":
                raise RuntimeError(f"Actor run did not succeed: status={status}")
            dataset_id = run.get("defaultDatasetId") or run.get("default_dataset_id")

            if not dataset_id:
                raise RuntimeError(f"Actor run returned no default dataset ID. status={status}")

            items = download_dataset_items(client, str(dataset_id))

            overwrite_jsonl(
                items_file,
                items,
            )

            all_items.extend(items)
            batch_record["dataset_item_count"] = len(items)
            batch_record.update(
                checkpoint="completed", items_sha256=sha256(items_file), finished_at=utc_now()
            )
            batch_record.pop("error", None)
            save_record()

            print(f"Batch {batch_index}: status={status}, dataset items={len(items)}")

        except KeyboardInterrupt:
            if batch_record.get("checkpoint") == "launching":
                batch_record["checkpoint"] = "launch_unknown"
            save_record()
            print("\nInterrupted by user.", file=sys.stderr)
            interrupted = True
            break

        except Exception as exc:
            if batch_record.get("checkpoint") == "launching":
                batch_record["checkpoint"] = (
                    "launch_rejected"
                    if isinstance(exc, ApifyApiError) and exc.status_code in {401, 403}
                    else "launch_unknown"
                )
            batch_record.update(failed_at=utc_now(), error=redact(f"{type(exc).__name__}: {exc}"))
            failed_batches.append(dict(batch_record))
            save_record()
            print(
                redact(f"[BATCH FAILED] {batch_profiles}: {exc}"),
                file=sys.stderr,
            )

    overwrite_jsonl(out / "raw" / "all_items.jsonl", all_items)
    error_records = [item for item in all_items if item.get("error") or item.get("errorCode")]
    overwrite_jsonl(out / "raw" / "errors.jsonl", error_records)

    normalized_rows, counts = split_and_write(all_items, out)

    elapsed = time.time() - started

    manifest = {
        "actor": ACTOR,
        "started_at": run_info["started_at"],
        "finished_at": utc_now(),
        "elapsed_seconds": round(elapsed, 2),
        "requested_accounts": accounts,
        "requested_account_count": len(accounts),
        "raw_dataset_items": len(all_items),
        "error_records": len(error_records),
        "normalized_rows": len(normalized_rows),
        "records_per_account": counts,
        "failed_batches": failed_batches,
        "interrupted": interrupted,
        "paths": {
            "raw_all": str(out / "raw" / "all_items.jsonl"),
            "profiles": str(out / "profiles"),
            "posts_by_account": str(out / "posts"),
            "normalized_jsonl": str(out / "normalized" / "posts.jsonl"),
            "normalized_csv": str(out / "normalized" / "posts.csv"),
        },
    }

    json_dump(manifest, out / "manifest.json")

    run_info["finished_at"] = manifest["finished_at"]
    run_info["manifest"] = manifest
    json_dump(run_info, out / "run_info.json")

    print()
    print("=" * 72)
    print("DONE")
    print("=" * 72)
    print(f"Output directory     : {out}")
    print(f"Requested profiles   : {len(accounts)}")
    print(f"Raw dataset items    : {len(all_items)}")
    print(f"Normalized rows      : {len(normalized_rows)}")
    print(f"Failed batches       : {len(failed_batches)}")

    print()
    print("Per-account records:")
    for account in accounts:
        print(f"  @{account}: {counts.get(account, 0)}")

    print()
    print("Next useful files:")
    print(f"  {out / 'manifest.json'}")
    print(f"  {out / 'normalized' / 'posts.csv'}")
    print(f"  {out / 'normalized' / 'posts.jsonl'}")
    print(f"  {out / 'raw' / 'all_items.jsonl'}")

    if interrupted:
        raise KeyboardInterrupt
    if failed_batches or error_records:
        raise ApplicationError("Capture completed with failures; successful records are retained.")
    return manifest
