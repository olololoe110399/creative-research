#!/usr/bin/env python3
"""
prepare_tiktok_media_v2.py

Prepare/download TikTok media from the merged raw dataset.

Key changes vs v1
-----------------
1) Prefer original TikTok CDN URLs:
   - slideshowImageLinks[].tiktokLink
   - videoMeta.originalCoverUrl
   - authorMeta.originalAvatarUrl

2) Fall back to Apify URLs only if TikTok CDN fails:
   - slideshowImageLinks[].downloadLink
   - videoMeta.coverUrl
   - authorMeta.avatar

3) Supports multiple Apify tokens:
   - APIFY_TOKENS="token1,token2,token3"
   - APIFY_TOKEN_1, APIFY_TOKEN_2, ...
   - APIFY_TOKEN as last fallback

4) NEVER sends Apify Authorization headers to TikTok/CDN hosts.

5) Checkpoints media_manifest.jsonl after every chunk, so Ctrl+C preserves progress.

Install
-------
    python -m pip install -U httpx

Recommended token setup
-----------------------
    export APIFY_TOKEN_1="..."
    export APIFY_TOKEN_2="..."
    export APIFY_TOKEN_3="..."
    export APIFY_TOKENS="$APIFY_TOKEN_1,$APIFY_TOKEN_2,$APIFY_TOKEN_3"

Run
---
    python prepare_tiktok_media_v2.py \
      selected_accounts \
      --out creative_media

Specific accounts
-----------------
    python prepare_tiktok_media_v2.py \
      selected_accounts \
      --accounts nickystudy12 estudio1252 \
      --out selected_media
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


TIKTOK_REFERER = "https://www.tiktok.com/"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def clean_username(value: str) -> str:
    value = (value or "").strip()
    m = re.search(r"tiktok\.com/@([^/?#]+)", value, flags=re.I)
    if m:
        value = m.group(1)
    return value.lstrip("@").strip("/")


def safe_name(value: str, max_len: int = 120) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^a-zA-Z0-9._@-]+", "_", value)
    value = value.strip("._")
    return value[:max_len] or "unknown"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[bad json] {path}:{line_no}: {exc}", file=sys.stderr)
                continue

            if isinstance(obj, dict):
                rows.append(obj)

    return rows


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def account_from_post(post: dict[str, Any], fallback: str = "") -> str:
    author = post.get("authorMeta") or {}
    for value in (
        post.get("input"),
        author.get("name") if isinstance(author, dict) else None,
        fallback,
    ):
        if isinstance(value, str) and value.strip():
            return clean_username(value)
    return "unknown"


def post_id(post: dict[str, Any]) -> str:
    for key in ("id", "idStr", "postId", "awemeId", "aweme_id"):
        value = post.get(key)
        if value is not None:
            return str(value)

    url = post.get("webVideoUrl") or post.get("url")
    if url:
        m = re.search(r"/video/(\d+)", str(url))
        if m:
            return m.group(1)

    payload = json.dumps(post, sort_keys=True, ensure_ascii=False, default=str)
    return "sha1_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def load_apify_tokens() -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    # 1) Comma-separated list.
    raw = os.environ.get("APIFY_TOKENS", "")
    for part in raw.split(","):
        token = part.strip()
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)

    # 2) Numbered env vars.
    numbered = []
    for key, value in os.environ.items():
        m = re.fullmatch(r"APIFY_TOKEN_(\d+)", key)
        if m and value.strip():
            numbered.append((int(m.group(1)), value.strip()))

    for _, token in sorted(numbered):
        if token not in seen:
            seen.add(token)
            tokens.append(token)

    # 3) Single fallback.
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if token and token not in seen:
        tokens.append(token)

    return tokens


def is_apify_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return (
        host.endswith("apify.com")
        or host.endswith("apifyusercontent.com")
        or host.endswith("apifyusercontent.com")
    )


def is_tiktokish_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return (
        "tiktok" in host
        or "tiktokcdn" in host
        or "byteoversea" in host
        or "ibyteimg" in host
        or "muscdn" in host
        or "akamaized" in host
    )


def extension_from_url(url: str, fallback: str = ".jpg") -> str:
    try:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix and 1 < len(suffix) <= 8:
            return suffix
    except Exception:
        pass
    return fallback


def compact_meta(post: dict[str, Any]) -> dict[str, Any]:
    author = post.get("authorMeta") or {}
    video = post.get("videoMeta") or {}
    music = post.get("musicMeta") or {}

    hashtags: list[str] = []
    for item in post.get("hashtags") or []:
        if isinstance(item, str):
            hashtags.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("title")
            if name:
                hashtags.append(str(name))

    return {
        "post_id": post_id(post),
        "account": account_from_post(post),
        "url": post.get("webVideoUrl"),
        "caption": post.get("text"),
        "created_at": post.get("createTimeISO"),
        "is_slideshow": bool(post.get("isSlideshow")),
        "is_pinned": bool(post.get("isPinned")),
        "is_ad": bool(post.get("isAd")),
        "is_sponsored": bool(post.get("isSponsored")),
        "views": post.get("playCount"),
        "likes": post.get("diggCount"),
        "comments": post.get("commentCount"),
        "shares": post.get("shareCount"),
        "saves": post.get("collectCount"),
        "reposts": post.get("repostCount"),
        "hashtags": hashtags,
        "slide_count": len(post.get("slideshowImageLinks") or []),
        "author": {
            "id": author.get("id") if isinstance(author, dict) else None,
            "name": author.get("name") if isinstance(author, dict) else None,
            "nickname": author.get("nickName") if isinstance(author, dict) else None,
            "followers": author.get("fans") if isinstance(author, dict) else None,
            "following": author.get("following") if isinstance(author, dict) else None,
            "total_likes": author.get("heart") if isinstance(author, dict) else None,
            "total_videos": author.get("video") if isinstance(author, dict) else None,
        },
        "music": {
            "id": music.get("musicId") if isinstance(music, dict) else None,
            "name": music.get("musicName") if isinstance(music, dict) else None,
            "author": music.get("musicAuthor") if isinstance(music, dict) else None,
        },
        "cover_original_url": (
            video.get("originalCoverUrl") if isinstance(video, dict) else None
        ),
        "cover_apify_url": (
            video.get("coverUrl") if isinstance(video, dict) else None
        ),
        "avatar_original_url": (
            author.get("originalAvatarUrl") if isinstance(author, dict) else None
        ),
        "avatar_apify_url": (
            author.get("avatar") if isinstance(author, dict) else None
        ),
    }


def make_candidates(
    primary_url: str | None,
    fallback_url: str | None,
    primary_label: str,
    fallback_label: str,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for label, url in (
        (primary_label, primary_url),
        (fallback_label, fallback_url),
    ):
        if not url or not isinstance(url, str):
            continue
        url = url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"source": label, "url": url})

    return out


def media_jobs_for_post(
    post: dict[str, Any],
    post_dir: Path,
    include_cover: bool,
    include_slides: bool,
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []

    pid = post_id(post)
    account = account_from_post(post)

    if include_cover:
        video = post.get("videoMeta") or {}
        if isinstance(video, dict):
            candidates = make_candidates(
                video.get("originalCoverUrl"),
                video.get("coverUrl"),
                "tiktok_original_cover",
                "apify_cover",
            )
            if candidates:
                jobs.append(
                    {
                        "kind": "cover",
                        "account": account,
                        "post_id": pid,
                        "index": None,
                        "candidates": candidates,
                        "path": post_dir / "cover.jpg",
                    }
                )

    if include_slides:
        for idx, item in enumerate(
            post.get("slideshowImageLinks") or [],
            start=1,
        ):
            if not isinstance(item, dict):
                continue

            candidates = make_candidates(
                item.get("tiktokLink"),
                item.get("downloadLink"),
                "tiktok_slide",
                "apify_slide",
            )
            if not candidates:
                continue

            jobs.append(
                {
                    "kind": "slide",
                    "account": account,
                    "post_id": pid,
                    "index": idx,
                    "candidates": candidates,
                    "path": post_dir / f"slide_{idx:03d}.jpg",
                }
            )

    return jobs


def avatar_job_for_post(
    post: dict[str, Any],
    out: Path,
) -> dict[str, Any] | None:
    account = account_from_post(post)
    author = post.get("authorMeta") or {}
    if not isinstance(author, dict):
        return None

    candidates = make_candidates(
        author.get("originalAvatarUrl"),
        author.get("avatar"),
        "tiktok_original_avatar",
        "apify_avatar",
    )
    if not candidates:
        return None

    return {
        "kind": "avatar",
        "account": account,
        "post_id": None,
        "index": None,
        "candidates": candidates,
        "path": out / safe_name(account) / "profile" / "avatar.jpg",
    }


async def fetch_candidate(
    client: httpx.AsyncClient,
    candidate: dict[str, str],
    tokens: list[str],
    timeout: float,
    retries: int,
) -> tuple[bytes | None, dict[str, Any]]:
    url = candidate["url"]
    source = candidate["source"]

    attempt_log: dict[str, Any] = {
        "source": source,
        "url": url,
        "attempts": [],
    }

    # Never send Apify tokens to non-Apify hosts.
    auth_variants: list[tuple[str, str | None]]
    if is_apify_url(url):
        # Public request first, then token rotation.
        auth_variants = [("no_auth", None)]
        auth_variants.extend(
            (f"token_{i}", token)
            for i, token in enumerate(tokens, start=1)
        )
    else:
        auth_variants = [("no_auth", None)]

    for auth_name, token in auth_variants:
        headers = {"User-Agent": DEFAULT_UA}

        if is_tiktokish_url(url):
            headers["Referer"] = TIKTOK_REFERER

        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        for retry in range(retries + 1):
            try:
                response = await client.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=True,
                )

                attempt_log["attempts"].append(
                    {
                        "auth": auth_name,
                        "retry": retry,
                        "http_status": response.status_code,
                        "bytes": len(response.content),
                    }
                )

                if response.status_code == 200 and response.content:
                    return response.content, attempt_log

                # Auth errors: move directly to next token.
                if response.status_code in {401, 403}:
                    break

                # Permanent missing/expired resource.
                if response.status_code in {404, 410}:
                    break

                # Retry transient errors.
                if response.status_code == 429 or response.status_code >= 500:
                    if retry < retries:
                        await asyncio.sleep(min(2 ** (retry + 1), 6))
                        continue
                    break

                # Other 4xx: no retry.
                break

            except Exception as exc:
                attempt_log["attempts"].append(
                    {
                        "auth": auth_name,
                        "retry": retry,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if retry < retries:
                    await asyncio.sleep(min(2 ** (retry + 1), 6))

    return None, attempt_log


async def download_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    job: dict[str, Any],
    tokens: list[str],
    retries: int,
    timeout: float,
    dry_run: bool,
) -> dict[str, Any]:
    path: Path = job["path"]

    result: dict[str, Any] = {
        "kind": job["kind"],
        "account": job["account"],
        "post_id": job.get("post_id"),
        "index": job.get("index"),
        "path": str(path),
        "status": None,
        "bytes": 0,
        "used_source": None,
        "attempt_log": [],
    }

    if path.exists() and path.stat().st_size > 0:
        result["status"] = "existing"
        result["bytes"] = path.stat().st_size
        return result

    if dry_run:
        result["status"] = "dry_run"
        return result

    path.parent.mkdir(parents=True, exist_ok=True)

    async with sem:
        for candidate in job["candidates"]:
            body, attempt_log = await fetch_candidate(
                client=client,
                candidate=candidate,
                tokens=tokens,
                timeout=timeout,
                retries=retries,
            )
            result["attempt_log"].append(attempt_log)

            if body:
                path.write_bytes(body)
                result["status"] = "downloaded"
                result["bytes"] = len(body)
                result["used_source"] = candidate["source"]
                return result

    result["status"] = "failed"

    # Make a concise summary for easy debugging.
    summaries = []
    for c in result["attempt_log"]:
        codes = [
            str(a.get("http_status"))
            for a in c.get("attempts", [])
            if a.get("http_status") is not None
        ]
        errors = [
            a.get("error")
            for a in c.get("attempts", [])
            if a.get("error")
        ]
        summaries.append(
            {
                "source": c.get("source"),
                "http_statuses": codes,
                "errors": errors[-2:],
            }
        )
    result["failure_summary"] = summaries

    return result


def load_previous_results(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    rows = read_jsonl(path)
    done_paths: set[str] = set()

    for row in rows:
        if row.get("status") in {"downloaded", "existing"}:
            p = row.get("path")
            if p and Path(p).exists() and Path(p).stat().st_size > 0:
                done_paths.add(str(Path(p)))

    return rows, done_paths


async def run(args: argparse.Namespace) -> None:
    root = Path(args.input).expanduser().resolve()
    posts_dir = root / "posts"

    if not posts_dir.exists():
        raise SystemExit(f"Missing posts directory: {posts_dir}")

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    selected = None
    if args.accounts:
        selected = {clean_username(x).lower() for x in args.accounts}

    posts: list[dict[str, Any]] = []

    for file in sorted(posts_dir.glob("*.jsonl")):
        fallback_account = clean_username(file.stem)

        if selected and fallback_account.lower() not in selected:
            continue

        for post in read_jsonl(file):
            acc = account_from_post(post, fallback_account)

            if selected and acc.lower() not in selected:
                continue

            post["_source_file"] = file.name
            posts.append(post)

    # De-duplicate by account + post_id.
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for post in posts:
        acc = account_from_post(post)
        deduped[(acc.lower(), post_id(post))] = post

    posts = list(deduped.values())
    posts.sort(
        key=lambda p: (
            account_from_post(p).lower(),
            str(p.get("createTimeISO") or ""),
            post_id(p),
        )
    )

    tokens = load_apify_tokens()

    print(f"Input: {root}")
    print(f"Unique posts: {len(posts)}")
    print(f"Apify fallback tokens detected: {len(tokens)}")

    all_jobs: list[dict[str, Any]] = []
    avatar_jobs: dict[str, dict[str, Any]] = {}
    post_manifest: list[dict[str, Any]] = []

    for post in posts:
        acc = account_from_post(post)
        pid = post_id(post)
        post_dir = out / safe_name(acc) / pid

        raw_copy = dict(post)
        raw_copy.pop("_source_file", None)

        write_json(post_dir / "raw.json", raw_copy)
        write_json(post_dir / "meta.json", compact_meta(post))

        all_jobs.extend(
            media_jobs_for_post(
                post,
                post_dir,
                include_cover=not args.no_covers,
                include_slides=not args.no_slides,
            )
        )

        if not args.no_avatars and acc.lower() not in avatar_jobs:
            avatar_job = avatar_job_for_post(post, out)
            if avatar_job:
                avatar_jobs[acc.lower()] = avatar_job

        post_manifest.append(
            {
                "account": acc,
                "post_id": pid,
                "url": post.get("webVideoUrl"),
                "created_at": post.get("createTimeISO"),
                "is_slideshow": bool(post.get("isSlideshow")),
                "slide_count": len(post.get("slideshowImageLinks") or []),
                "views": post.get("playCount"),
                "likes": post.get("diggCount"),
                "comments": post.get("commentCount"),
                "shares": post.get("shareCount"),
                "saves": post.get("collectCount"),
                "post_dir": str(post_dir),
            }
        )

    all_jobs.extend(avatar_jobs.values())
    write_jsonl(out / "post_manifest.jsonl", post_manifest)

    manifest_path = out / "media_manifest.jsonl"
    previous_rows, previously_done_paths = load_previous_results(manifest_path)

    # Existing actual files are also considered complete, even if manifest was interrupted.
    filtered_jobs: list[dict[str, Any]] = []
    for job in all_jobs:
        path = Path(job["path"])
        if (
            str(path) in previously_done_paths
            or (path.exists() and path.stat().st_size > 0)
        ):
            continue
        filtered_jobs.append(job)

    print(f"Media jobs total: {len(all_jobs)}")
    print(
        f"  slides: {sum(j['kind'] == 'slide' for j in all_jobs)} | "
        f"covers: {sum(j['kind'] == 'cover' for j in all_jobs)} | "
        f"avatars: {sum(j['kind'] == 'avatar' for j in all_jobs)}"
    )
    print(f"Already completed/skipped: {len(all_jobs) - len(filtered_jobs)}")
    print(f"Remaining jobs: {len(filtered_jobs)}")

    if args.dry_run:
        print("Dry run: no media will be downloaded.")

    limits = httpx.Limits(
        max_connections=max(args.concurrency * 2, 20),
        max_keepalive_connections=max(args.concurrency, 10),
    )

    sem = asyncio.Semaphore(args.concurrency)
    current_rows = list(previous_rows)

    async with httpx.AsyncClient(limits=limits, http2=False) as client:
        try:
            for start in range(0, len(filtered_jobs), args.checkpoint_every):
                chunk = filtered_jobs[start : start + args.checkpoint_every]

                tasks = [
                    asyncio.create_task(
                        download_one(
                            client=client,
                            sem=sem,
                            job=job,
                            tokens=tokens,
                            retries=args.retries,
                            timeout=args.timeout,
                            dry_run=args.dry_run,
                        )
                    )
                    for job in chunk
                ]

                chunk_results = await asyncio.gather(*tasks)
                current_rows.extend(chunk_results)

                # Checkpoint after every chunk.
                write_jsonl(manifest_path, current_rows)

                counts: dict[str, int] = {}
                source_counts: dict[str, int] = {}

                for row in current_rows:
                    status = str(row.get("status"))
                    counts[status] = counts.get(status, 0) + 1
                    source = row.get("used_source")
                    if source:
                        source_counts[source] = source_counts.get(source, 0) + 1

                done = min(start + len(chunk), len(filtered_jobs))
                print(
                    f"[{done}/{len(filtered_jobs)} remaining] "
                    f"status={counts} sources={source_counts}"
                )

        except KeyboardInterrupt:
            print("\nInterrupted. Checkpoint already saved.", file=sys.stderr)

    # Final report from manifest.
    final_rows = read_jsonl(manifest_path)

    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    failed_examples: list[dict[str, Any]] = []

    for row in final_rows:
        status = str(row.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1

        source = row.get("used_source")
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1

        if status == "failed" and len(failed_examples) < 30:
            failed_examples.append(row)

    report = {
        "input": str(root),
        "output": str(out),
        "accounts": sorted({account_from_post(p) for p in posts}),
        "account_count": len({account_from_post(p) for p in posts}),
        "posts": len(posts),
        "slideshow_posts": sum(bool(p.get("isSlideshow")) for p in posts),
        "video_posts": sum(not bool(p.get("isSlideshow")) for p in posts),
        "slide_images_expected": sum(
            len(p.get("slideshowImageLinks") or []) for p in posts
        ),
        "media_jobs_total": len(all_jobs),
        "status_counts": status_counts,
        "source_counts": source_counts,
        "apify_tokens_detected": len(tokens),
        "failed_examples": failed_examples,
        "dry_run": args.dry_run,
    }

    write_json(out / "download_report.json", report)

    print()
    print("=" * 72)
    print("DONE / CHECKPOINTED")
    print("=" * 72)
    print(f"Posts                 : {report['posts']}")
    print(f"Slideshow posts       : {report['slideshow_posts']}")
    print(f"Video posts           : {report['video_posts']}")
    print(f"Expected slide images : {report['slide_images_expected']}")
    print(f"Media status          : {status_counts}")
    print(f"Sources used          : {source_counts}")
    print(f"Apify tokens detected : {len(tokens)}")
    print(f"Output                : {out}")
    print(f"Report                : {out / 'download_report.json'}")

    if status_counts.get("failed"):
        print()
        print(
            "There are failed items. Check download_report.json -> failed_examples.\n"
            "Typical meanings:\n"
            "  TikTok 403/404 + Apify 404/410: both signed CDN URL and KVS object expired.\n"
            "  Apify 401/403 on all tokens: none of the configured tokens can access that KVS.\n"
            "  TikTok success: no Apify token was needed for that file."
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Organize/download TikTok slideshow/cover media. "
            "Prefer TikTok CDN and rotate Apify tokens only as fallback."
        )
    )

    p.add_argument(
        "input",
        help="Merged TikTok dataset folder containing posts/*.jsonl",
    )
    p.add_argument(
        "--out",
        default="tiktok_media",
        help="Output directory",
    )
    p.add_argument(
        "--accounts",
        nargs="*",
        help="Optional usernames; if omitted, process all accounts",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=12,
        help="Concurrent downloads. Default: 12",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=35.0,
        help="HTTP timeout seconds. Default: 35",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retries for transient 429/5xx/network errors. Default: 1",
    )
    p.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Save manifest every N attempted jobs. Default: 100",
    )
    p.add_argument(
        "--no-slides",
        action="store_true",
        help="Do not download slideshow images",
    )
    p.add_argument(
        "--no-covers",
        action="store_true",
        help="Do not download cover images",
    )
    p.add_argument(
        "--no-avatars",
        action="store_true",
        help="Do not download profile avatars",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build folders/manifests but do not download media",
    )

    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    if args.retries < 0:
        raise SystemExit("--retries cannot be negative")
    if args.checkpoint_every < 1:
        raise SystemExit("--checkpoint-every must be >= 1")

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nStopped by user. Existing files and last checkpoint are preserved.")


if __name__ == "__main__":
    main()
