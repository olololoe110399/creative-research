"""Archive TikTok media with bounded concurrency and resumable checkpoints.

Prefer source CDN URLs; use Apify fallback without sending tokens to other hosts.
Credentials are explicit environment values. See the installed command help.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from creative_research.capture.cache import attest, fingerprint, verified
from creative_research.identity import clean_account_handle
from creative_research.infrastructure.logging import redact
from creative_research.infrastructure.paths import confined_path, resolve_path
from creative_research.infrastructure.storage import (
    read_jsonl,
    write_bytes,
    write_json,
    write_jsonl,
)

TIKTOK_REFERER = "https://www.tiktok.com/"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class MediaArchiveOptions:
    """CLI-independent parameters for this workflow."""

    input: str
    out: str
    accounts: list[str] | None
    concurrency: int
    timeout: float
    retries: int
    checkpoint_every: int
    no_slides: bool
    no_covers: bool
    no_avatars: bool
    dry_run: bool


def account_from_post(post: dict[str, Any], fallback: str = "") -> str:
    author = post.get("authorMeta") or {}
    for value in (
        post.get("account"),
        post.get("input"),
        author.get("name") if isinstance(author, dict) else None,
        fallback or Path(str(post.get("_source_file") or "")).stem,
    ):
        if isinstance(value, str) and value.strip():
            return clean_account_handle(value)
    return "unknown"


def post_id(post: dict[str, Any]) -> str:
    for key in ("post_id", "id", "idStr", "postId", "awemeId", "aweme_id"):
        value = post.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    for key in ("webVideoUrl", "url", "postUrl"):
        m = re.search(r"/(?:video|photo)/(\d+)", str(post.get(key) or ""))
        if m:
            return m.group(1)

    raw = {key: value for key, value in post.items() if key != "_source_file"}
    payload = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
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
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        host == domain or host.endswith("." + domain)
        for domain in ("apify.com", "apifyusercontent.com")
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
        "cover_original_url": (video.get("originalCoverUrl") if isinstance(video, dict) else None),
        "cover_apify_url": (video.get("coverUrl") if isinstance(video, dict) else None),
        "avatar_original_url": (
            author.get("originalAvatarUrl") if isinstance(author, dict) else None
        ),
        "avatar_apify_url": (author.get("avatar") if isinstance(author, dict) else None),
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
                        "path": confined_path(post_dir, "cover.jpg"),
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
                    "path": confined_path(post_dir, f"slide_{idx:03d}.jpg"),
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
        "path": confined_path(out, account, "profile", "avatar.jpg"),
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
        auth_variants.extend((f"token_{i}", token) for i, token in enumerate(tokens, start=1))
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
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if (
                        not content_type
                        or content_type.lower().startswith("image/")
                        or (content_type.lower() == "application/octet-stream")
                    ):
                        return response.content, attempt_log
                    attempt_log["attempts"][-1]["error"] = (
                        f"Unexpected image content-type: {content_type}"
                    )
                    break

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
                        "error": redact(f"{type(exc).__name__}: {exc}"),
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
    source = fingerprint({key: value for key, value in job.items() if key != "path"})
    cached = verified(path, source)
    if cached:
        result["status"] = "existing"
        result["bytes"] = path.stat().st_size
        result.update(cached)
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
                write_bytes(path, body)
                result.update(attest(path, source))
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
        errors = [a.get("error") for a in c.get("attempts", []) if a.get("error")]
        summaries.append(
            {
                "source": c.get("source"),
                "http_statuses": codes,
                "errors": errors[-2:],
            }
        )
    result["failure_summary"] = summaries

    return result


async def archive_media(options: MediaArchiveOptions) -> dict[str, Any]:

    if options.concurrency < 1 or options.checkpoint_every < 1 or options.retries < 0:
        raise ValueError("Concurrency/checkpoint must be positive; retries cannot be negative")
    if not math.isfinite(options.timeout) or options.timeout <= 0:
        raise ValueError("Timeout must be finite and positive")
    root, out = resolve_path(options.input), resolve_path(options.out)
    if out.is_relative_to(root) or root.is_relative_to(out):
        raise ValueError("Media output overlaps the source dataset")
    posts_dir = root / "posts"
    if not posts_dir.is_dir():
        raise FileNotFoundError(f"Missing posts directory: {posts_dir}")
    selected = {clean_account_handle(x).casefold() for x in options.accounts or []}
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for file in sorted(posts_dir.glob("*.jsonl")):
        if not file.resolve().is_relative_to(root):
            raise ValueError("Source post file escapes input root")
        for raw in read_jsonl(file):
            account = account_from_post(raw, file.stem)
            if selected and account.casefold() not in selected:
                continue
            key = account.casefold(), post_id(raw)
            if (
                key in unique
                and {k: v for k, v in unique[key].items() if k != "_source_file"} != raw
            ):
                raise ValueError(f"Conflicting source post: {key}")
            post = dict(raw, _source_file=file.name)
            unique[key] = post
    posts = [unique[key] for key in sorted(unique)]
    if not posts:
        raise ValueError("No matching posts in input dataset")
    # Preflight every path and job before writing or opening a connection.
    destinations = [confined_path(out, account_from_post(p), post_id(p)) for p in posts]
    jobs: list[dict[str, Any]] = []
    avatars: dict[str, dict[str, Any]] = {}
    for post, directory in zip(posts, destinations, strict=True):
        confined_path(directory, "raw.json")
        confined_path(directory, "meta.json")
        jobs.extend(
            media_jobs_for_post(post, directory, not options.no_covers, not options.no_slides)
        )
        avatar = avatar_job_for_post(post, out) if not options.no_avatars else None
        if avatar:
            avatars.setdefault(account_from_post(post).casefold(), avatar)
    jobs.extend(avatars.values())
    for job in jobs:
        job["snapshot_fingerprint"] = (
            fingerprint(
                {
                    key: value
                    for key, value in unique[(job["account"].casefold(), job["post_id"])].items()
                    if key != "_source_file"
                }
            )
            if job.get("post_id")
            else fingerprint(job["candidates"])
        )
    report: dict[str, Any] = {
        "posts": len(posts),
        "accounts": sorted({account_from_post(p) for p in posts}),
        "post_keys": [(account_from_post(p), post_id(p)) for p in posts],
        "video_posts": sum(
            not bool(p.get("isSlideshow", p.get("slideshowImageLinks"))) for p in posts
        ),
        "media_jobs_total": len(jobs),
        "dry_run": options.dry_run,
    }
    if options.dry_run:
        report.update(
            failed=0,
            pending=sum(
                not Path(j["path"]).is_file() or Path(j["path"]).stat().st_size == 0 for j in jobs
            ),
        )
        return report
    for post, directory in zip(posts, destinations, strict=True):
        raw = {k: v for k, v in post.items() if k != "_source_file"}
        write_json(directory / "raw.json", raw)
        meta = compact_meta(post)
        meta["account"] = account_from_post(post)
        meta["is_slideshow"] = bool(post.get("isSlideshow", post.get("slideshowImageLinks")))
        write_json(directory / "meta.json", meta)
    manifest = out / "media_manifest.jsonl"
    rows: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(options.concurrency)
    limits = httpx.Limits(
        max_connections=options.concurrency, max_keepalive_connections=options.concurrency
    )
    async with httpx.AsyncClient(limits=limits) as client:
        try:
            for start in range(0, len(jobs), options.checkpoint_every):
                chunk = jobs[start : start + options.checkpoint_every]
                tasks = [
                    asyncio.create_task(
                        download_one(
                            client,
                            sem,
                            job,
                            load_apify_tokens(),
                            options.retries,
                            options.timeout,
                            False,
                        )
                    )
                    for job in chunk
                ]
                try:
                    results = await asyncio.gather(*tasks)
                except BaseException:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    rows.extend(
                        task.result()
                        for task in tasks
                        if not task.cancelled() and task.exception() is None
                    )
                    raise
                rows.extend(results)
                write_jsonl(manifest, rows)
        finally:
            write_jsonl(manifest, rows)
    report.update(
        failed=sum(row["status"] == "failed" for row in rows),
        status_counts={
            status: sum(row["status"] == status for row in rows)
            for status in ("downloaded", "existing", "failed")
        },
    )
    write_json(out / "image_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report
