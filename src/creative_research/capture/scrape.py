"""Archive confirmed public TikTok profiles through the explicit Apify command.

Capture metadata, per-account records and optional key-value media with configured
sample, timeout and cost caps. Installation and examples live in docs/.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from apify_client import ApifyClient

from creative_research.identity import clean_account_handle
from creative_research.infrastructure.config import RuntimeSettings
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import atomic_output, write_bytes
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
    download_videos: bool
    download_covers: bool
    download_slides: bool
    download_avatars: bool
    subtitles: str
    comments: int
    top_level_comments: int
    max_replies: int
    oldest_date: str | None
    newest_date: str | None
    skip_media_sync: bool
    operators: str
    operator_id: str | None
    preflight: bool


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


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


def safe_name(value: str, max_len: int = 120) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^a-zA-Z0-9._@-]+", "_", value)
    value = value.strip("._")
    return value[:max_len] or "unknown"


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


def deep_get(obj: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def first_value(item: dict[str, Any], paths: list[str], default: Any = None) -> Any:
    for path in paths:
        value = deep_get(item, path)
        if value is not None and value != "":
            return value
    return default


def guess_account(item: dict[str, Any]) -> str:
    candidates = [
        first_value(item, ["input"]),
        first_value(item, ["authorMeta.name"]),
        first_value(item, ["authorMeta.uniqueId"]),
        first_value(item, ["author.uniqueId"]),
        first_value(item, ["author.unique_id"]),
        first_value(item, ["authorMeta.nickName"]),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return clean_account_handle(value)
    return "unknown"


def guess_post_id(item: dict[str, Any]) -> str:
    value = first_value(
        item,
        [
            "id",
            "idStr",
            "postId",
            "awemeId",
            "aweme_id",
            "videoMeta.id",
            "video.id",
        ],
    )
    if value is not None:
        return str(value)

    payload = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    return "sha1_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def normalize_post(item: dict[str, Any]) -> dict[str, Any]:
    account = guess_account(item)
    author = item.get("authorMeta") or item.get("author") or {}
    video = item.get("videoMeta") or item.get("video") or {}
    music = item.get("musicMeta") or item.get("music") or {}

    hashtags = item.get("hashtags")
    hashtag_values: list[str] = []
    if isinstance(hashtags, list):
        for x in hashtags:
            if isinstance(x, str):
                hashtag_values.append(x)
            elif isinstance(x, dict):
                hashtag_values.append(
                    str(x.get("name") or x.get("title") or x.get("hashtagName") or "")
                )
            else:
                hashtag_values.append(str(x))
        hashtag_values = [x for x in hashtag_values if x]

    return {
        "account": account,
        "post_id": guess_post_id(item),
        "url": first_value(
            item,
            ["webVideoUrl", "url", "postUrl", "videoUrl", "shareUrl"],
        ),
        "caption": first_value(
            item,
            ["text", "desc", "description", "caption"],
            "",
        ),
        "created_at": first_value(
            item,
            [
                "createTimeISO",
                "createTime",
                "create_time",
                "timestamp",
                "publishedAt",
            ],
        ),
        "is_pinned": first_value(
            item,
            ["isPinned", "pinned", "is_pinned"],
            False,
        ),
        "views": first_value(
            item,
            ["playCount", "stats.playCount", "stats.play_count", "views"],
        ),
        "likes": first_value(
            item,
            ["diggCount", "stats.diggCount", "stats.likeCount", "likes"],
        ),
        "comments": first_value(
            item,
            ["commentCount", "stats.commentCount", "comments"],
        ),
        "shares": first_value(
            item,
            ["shareCount", "stats.shareCount", "shares"],
        ),
        "saves": first_value(
            item,
            ["collectCount", "stats.collectCount", "stats.saveCount", "saves"],
        ),
        "hashtags": hashtag_values,
        "author_id": author.get("id") if isinstance(author, dict) else None,
        "author_name": author.get("name") if isinstance(author, dict) else None,
        "author_nickname": (author.get("nickName") if isinstance(author, dict) else None),
        "followers": author.get("fans") if isinstance(author, dict) else None,
        "following": author.get("following") if isinstance(author, dict) else None,
        "author_total_likes": (author.get("heart") if isinstance(author, dict) else None),
        "author_total_videos": (author.get("video") if isinstance(author, dict) else None),
        "video_duration": (video.get("duration") if isinstance(video, dict) else None),
        "video_width": video.get("width") if isinstance(video, dict) else None,
        "video_height": video.get("height") if isinstance(video, dict) else None,
        "music_name": (
            (music.get("musicName") or music.get("title") or music.get("name"))
            if isinstance(music, dict)
            else None
        ),
        "music_author": (
            (music.get("musicAuthor") or music.get("authorName") or music.get("author"))
            if isinstance(music, dict)
            else None
        ),
        "error": item.get("error"),
        "error_code": item.get("errorCode"),
    }


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
    media_store_name: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profiles": profiles,
        "profileScrapeSections": ["videos"],
        "profileSorting": "latest",
        "resultsPerPage": args.max_posts,
        "excludePinnedPosts": False,
        "shouldDownloadVideos": bool(args.download_videos),
        "shouldDownloadCovers": bool(args.download_covers),
        "shouldDownloadSlideshowImages": bool(args.download_slides),
        "shouldDownloadAvatars": bool(args.download_avatars),
        "downloadSubtitlesOptions": args.subtitles,
        "commentsPerPost": args.comments,
        "topLevelCommentsPerPost": args.top_level_comments,
        "maxRepliesPerComment": args.max_replies,
    }

    if media_store_name and (
        args.download_videos
        or args.download_covers
        or args.download_slides
        or args.download_avatars
        or args.subtitles != "NEVER_DOWNLOAD_SUBTITLES"
    ):
        payload["videoKvStoreIdOrName"] = media_store_name

    if args.oldest_date:
        payload["oldestPostDateUnified"] = args.oldest_date

    if args.newest_date:
        payload["newestPostDate"] = args.newest_date

    return payload


def run_actor_batch(
    client: ApifyClient,
    profiles: list[str],
    args: ScrapeOptions,
    media_store_name: str | None,
) -> dict[str, Any]:
    actor_input = build_actor_input(profiles, args, media_store_name)

    print()
    print("Starting Apify Actor batch:")
    for p in profiles:
        print(f"  @{p}")

    run = client.actor(ACTOR).call(
        run_input=actor_input,
        run_timeout=timedelta(seconds=args.actor_timeout),
        max_total_charge_usd=Decimal(str(args.max_charge_usd))
        if args.max_charge_usd is not None
        else None,
    )

    if run is None:
        raise RuntimeError("Apify did not return a run object.")

    return to_plain(run)


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


def kv_key_name(key_obj: Any) -> str:
    if isinstance(key_obj, dict):
        return str(key_obj.get("key") or key_obj.get("name") or key_obj.get("id") or "")

    for attr in ("key", "name", "id"):
        if hasattr(key_obj, attr):
            value = getattr(key_obj, attr)
            if value:
                return str(value)

    return str(key_obj)


def content_type_extension(content_type: str | None) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "text/vtt": ".vtt",
        "application/json": ".json",
        "text/plain": ".txt",
    }.get(ct, "")


def save_kv_value(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(value, bytes):
        write_bytes(path, value)
    elif isinstance(value, bytearray):
        write_bytes(path, bytes(value))
    elif isinstance(value, (dict, list)):
        atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str))
    elif value is None:
        write_bytes(path, b"")
    elif isinstance(value, str):
        atomic_write_text(path, value)
    else:
        atomic_write_text(path, str(value))


def mirror_kv_store(
    client: ApifyClient,
    store_id_or_name: str,
    out_dir: Path,
) -> dict[str, Any]:
    store = client.key_value_store(store_id_or_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0
    index_rows: list[dict[str, Any]] = []

    print()
    print(f"Mirroring media store: {store_id_or_name}")

    for key_obj in store.iterate_keys():
        key = kv_key_name(key_obj)
        if not key:
            continue

        try:
            record = store.get_record(key)
            if not record:
                failed += 1
                continue

            value = record.get("value")
            content_type = record.get("contentType") or record.get("content_type")

            raw_key = key.replace("\\", "/").lstrip("/")
            key_path = Path(raw_key)

            safe_parts = [
                safe_name(part, 100) for part in key_path.parts if part not in {"", ".", ".."}
            ]
            if not safe_parts:
                safe_parts = ["record_" + hashlib.sha1(key.encode()).hexdigest()[:12]]

            local_path = out_dir.joinpath(*safe_parts)

            if not local_path.suffix:
                ext = content_type_extension(content_type)
                if ext:
                    local_path = local_path.with_name(local_path.name + ext)

            if local_path.exists() and local_path.stat().st_size > 0:
                skipped += 1
            else:
                save_kv_value(local_path, value)
                downloaded += 1

            index_rows.append(
                {
                    "key": key,
                    "content_type": content_type,
                    "local_path": str(local_path),
                }
            )

            if (downloaded + skipped + failed) % 100 == 0:
                print(f"  media: {downloaded} downloaded, {skipped} existing, {failed} failed")

        except Exception as exc:
            failed += 1
            index_rows.append(
                {
                    "key": key,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"  [media error] {key}: {exc}")

    overwrite_jsonl(out_dir.parent / "media_index.jsonl", index_rows)

    return {
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "failed": failed,
        "total_seen": len(index_rows),
    }


def split_and_write(
    all_items: list[dict[str, Any]],
    out: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profiles: dict[str, dict[str, Any]] = {}
    normalized_rows: list[dict[str, Any]] = []
    seen_post_ids: set[tuple[str, str]] = set()

    for item in all_items:
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
    for account, rows in sorted(by_account.items()):
        overwrite_jsonl(posts_dir / f"{safe_name(account)}.jsonl", rows)

    profiles_dir = out / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    for account, profile in sorted(profiles.items()):
        json_dump(profile, profiles_dir / f"{safe_name(account)}.json")

    normalized_rows.sort(
        key=lambda x: (
            str(x.get("account") or "").lower(),
            str(x.get("created_at") or ""),
            str(x.get("post_id") or ""),
        )
    )

    overwrite_jsonl(out / "normalized" / "posts.jsonl", normalized_rows)
    write_normalized_csv(out / "normalized" / "posts.csv", normalized_rows)

    counts = {account: len(rows) for account, rows in sorted(by_account.items())}

    return normalized_rows, counts


def archive_posts(options: ScrapeOptions) -> None:

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

    from creative_research.operating.onboarding import checked_scrape_operator
    from creative_research.operating.registry import load_operator_registry

    accounts_file = resolve_path(options.accounts_file)
    accounts = read_accounts(accounts_file)
    try:
        registry_path = resolve_path(options.operators)
        registry = load_operator_registry(registry_path)
        operator = checked_scrape_operator(registry, accounts, operator_id=options.operator_id)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(
            f"Operator grouping preflight FAILED: {exc}\n"
            "Set it up with creative-research operator-setup "
            "--confirm-same-operator before scraping."
        ) from exc
    print(
        f"Operator grouping confirmed: {operator.operator_id} "
        f"({len(accounts)} requested accounts; researcher assertion)."
    )
    if options.preflight:
        print("Preflight PASS. No Apify token used or provider call made.")
        return

    token = options.token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit(
            "APIFY_TOKEN is missing.\n\n"
            "macOS/Linux:\n"
            '  export APIFY_TOKEN="apify_api_..."\n\n'
            "PowerShell:\n"
            '  $env:APIFY_TOKEN="apify_api_..."\n'
        )

    out = resolve_path(options.out)
    (out / "raw" / "batches").mkdir(parents=True, exist_ok=True)
    (out / "profiles").mkdir(parents=True, exist_ok=True)
    (out / "posts").mkdir(parents=True, exist_ok=True)
    (out / "normalized").mkdir(parents=True, exist_ok=True)
    (out / "media" / "kv").mkdir(parents=True, exist_ok=True)

    has_media = (
        options.download_videos
        or options.download_covers
        or options.download_slides
        or options.download_avatars
        or options.subtitles != "NEVER_DOWNLOAD_SUBTITLES"
    )

    media_store_name = f"creative-research-tiktok-{utc_stamp()}" if has_media else None

    run_info: dict[str, Any] = {
        "actor": ACTOR,
        "started_at": utc_now(),
        "accounts_file": str(accounts_file),
        "accounts": accounts,
        "operator_grouping": {
            "operator_id": operator.operator_id,
            "name": operator.name,
            "user_confirmed": True,
            "confirmation_method": operator.verification_method,
            "confirmation_date": operator.verified_at,
            "registry_path": str(registry_path),
            "not_legal_ownership_proof": True,
        },
        "account_count": len(accounts),
        "settings": {
            "batch_size": options.batch_size,
            "max_posts_per_profile": options.max_posts,
            "download_videos": options.download_videos,
            "download_covers": options.download_covers,
            "download_slides": options.download_slides,
            "download_avatars": options.download_avatars,
            "subtitles": options.subtitles,
            "comments_per_post": options.comments,
            "top_level_comments_per_post": options.top_level_comments,
            "max_replies_per_comment": options.max_replies,
            "oldest_date": options.oldest_date,
            "newest_date": options.newest_date,
            "max_charge_usd_per_batch": options.max_charge_usd,
        },
        "media_store_name": media_store_name,
        "batches": [],
    }
    json_dump(run_info, out / "run_info.json")

    atomic_write_text(out / "accounts.txt", "\n".join(accounts) + "\n")

    client = ApifyClient(
        token, timeout_medium=timedelta(seconds=RuntimeSettings.from_environ().request_timeout)
    )

    all_items: list[dict[str, Any]] = []
    failed_batches: list[dict[str, Any]] = []
    started = time.time()

    for batch_index, batch_profiles in enumerate(
        chunks(accounts, options.batch_size),
        start=1,
    ):
        batch_started = utc_now()

        try:
            run = run_actor_batch(
                client=client,
                profiles=batch_profiles,
                args=options,
                media_store_name=media_store_name,
            )

            status = str(run.get("status") or run.get("statusMessage") or "UNKNOWN")

            dataset_id = run.get("defaultDatasetId") or run.get("default_dataset_id")

            batch_record = {
                "batch_index": batch_index,
                "profiles": batch_profiles,
                "started_at": batch_started,
                "finished_at": utc_now(),
                "run_id": run.get("id"),
                "status": status,
                "dataset_id": dataset_id,
                "run": run,
            }

            json_dump(
                batch_record,
                out / "raw" / "batches" / f"batch_{batch_index:03d}_run.json",
            )

            if not dataset_id:
                raise RuntimeError(f"Actor run returned no default dataset ID. status={status}")

            items = download_dataset_items(client, str(dataset_id))

            overwrite_jsonl(
                out / "raw" / "batches" / f"batch_{batch_index:03d}_items.jsonl",
                items,
            )

            all_items.extend(items)
            batch_record["dataset_item_count"] = len(items)
            run_info["batches"].append(batch_record)
            json_dump(run_info, out / "run_info.json")

            print(f"Batch {batch_index}: status={status}, dataset items={len(items)}")

        except KeyboardInterrupt:
            print("\nInterrupted by user.", file=sys.stderr)
            break

        except Exception as exc:
            error_record = {
                "batch_index": batch_index,
                "profiles": batch_profiles,
                "started_at": batch_started,
                "failed_at": utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
            }
            failed_batches.append(error_record)
            run_info["batches"].append(error_record)
            json_dump(run_info, out / "run_info.json")
            print(
                f"[BATCH FAILED] {batch_profiles}: {exc}",
                file=sys.stderr,
            )

    overwrite_jsonl(out / "raw" / "all_items.jsonl", all_items)

    normalized_rows, counts = split_and_write(all_items, out)

    media_stats = None
    if media_store_name and not options.skip_media_sync:
        try:
            media_stats = mirror_kv_store(
                client,
                media_store_name,
                out / "media" / "kv",
            )
        except Exception as exc:
            media_stats = {"error": f"{type(exc).__name__}: {exc}"}
            print(
                f"[MEDIA SYNC FAILED] {exc}",
                file=sys.stderr,
            )

    elapsed = time.time() - started

    manifest = {
        "actor": ACTOR,
        "started_at": run_info["started_at"],
        "finished_at": utc_now(),
        "elapsed_seconds": round(elapsed, 2),
        "requested_accounts": accounts,
        "requested_account_count": len(accounts),
        "raw_dataset_items": len(all_items),
        "normalized_rows": len(normalized_rows),
        "records_per_account": counts,
        "failed_batches": failed_batches,
        "media_store_name": media_store_name,
        "media_sync": media_stats,
        "paths": {
            "raw_all": str(out / "raw" / "all_items.jsonl"),
            "profiles": str(out / "profiles"),
            "posts_by_account": str(out / "posts"),
            "normalized_jsonl": str(out / "normalized" / "posts.jsonl"),
            "normalized_csv": str(out / "normalized" / "posts.csv"),
            "media": str(out / "media" / "kv"),
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

    if media_store_name:
        print(f"Apify media KVS      : {media_store_name}")
    if media_stats:
        print(f"Media sync           : {media_stats}")

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
