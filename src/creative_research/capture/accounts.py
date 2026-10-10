"""Merge scrape snapshots for explicitly selected accounts without provider calls."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from creative_research.identity import clean_account_handle
from creative_research.infrastructure.paths import confined_path, resolve_path
from creative_research.infrastructure.storage import (
    atomic_output,
    read_jsonl,
    write_json,
    write_jsonl,
)


def _account_for_record(record: dict[str, Any]) -> str:
    for field in ("account", "input"):
        if record.get(field):
            return clean_account_handle(record[field])
    author = record.get("authorMeta") or record.get("author") or {}
    if isinstance(author, dict):
        for field in ("name", "uniqueId", "unique_id"):
            if author.get(field):
                return clean_account_handle(author[field])
    return ""


def _post_identity(record: dict[str, Any]) -> str:
    for field in ("post_id", "id", "idStr", "postId", "awemeId", "aweme_id"):
        if record.get(field) is not None:
            return str(record[field])
    for field in ("url", "webVideoUrl", "postUrl"):
        if record.get(field):
            return str(record[field])
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


def _merge_records(
    path: Path,
    accounts: dict[str, str],
    selected: dict[str, dict[str, dict[str, Any]]],
) -> None:
    for record in read_jsonl(path, missing_ok=True, tolerate_invalid=True):
        account_key = _account_for_record(record).lower()
        if account_key in accounts:
            selected[accounts[account_key]][_post_identity(record)] = record


def run(
    *,
    sources: list[str],
    accounts: list[str],
    out: str = "selected_accounts",
) -> None:

    accounts_frame = {
        clean_account_handle(value).lower(): clean_account_handle(value) for value in accounts
    }
    output = resolve_path(out)
    for handle in accounts_frame.values():
        if not handle:
            raise ValueError("Selected account handle must not be empty")
        confined_path(output, handle)
        confined_path(output, "posts", f"{handle}.jsonl")
        confined_path(output, "normalized", f"{handle}.jsonl")

    raw_posts: dict[str, dict[str, dict[str, Any]]] = {
        handle: {} for handle in accounts_frame.values()
    }
    normalized_posts: dict[str, dict[str, dict[str, Any]]] = {
        handle: {} for handle in accounts_frame.values()
    }
    for source in map(resolve_path, sources):
        _merge_records(source / "normalized/posts.jsonl", accounts_frame, normalized_posts)
        posts_directory = source / "posts"
        if posts_directory.exists():
            for path in sorted(posts_directory.glob("*.jsonl")):
                _merge_records(path, accounts_frame, raw_posts)
        _merge_records(source / "raw/all_items.jsonl", accounts_frame, raw_posts)

    all_normalized: list[dict[str, Any]] = []
    manifest: dict[str, dict[str, int]] = {}
    for handle in accounts_frame.values():
        raw = list(raw_posts[handle].values())
        normalized = list(normalized_posts[handle].values())
        write_jsonl(confined_path(output, "posts", f"{handle}.jsonl"), raw)
        write_jsonl(confined_path(output, "normalized", f"{handle}.jsonl"), normalized)
        all_normalized.extend(normalized)
        manifest[handle] = {"raw_posts": len(raw), "normalized_posts": len(normalized)}
    write_jsonl(output / "normalized/posts.jsonl", all_normalized)

    if all_normalized:
        fields = list(dict.fromkeys(field for record in all_normalized for field in record))
        with atomic_output(output / "normalized/posts.csv") as temporary:
            with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for record in all_normalized:
                    writer.writerow(
                        {
                            field: json.dumps(value, ensure_ascii=False)
                            if isinstance(value, (list, dict))
                            else value
                            for field, value in record.items()
                        }
                    )

    write_json(output / "manifest.json", {"sources": sources, "accounts": manifest})
    print("DONE:", output)
    for account, counts in manifest.items():
        print(f"@{account}: {counts['raw_posts']} raw | {counts['normalized_posts']} normalized")
