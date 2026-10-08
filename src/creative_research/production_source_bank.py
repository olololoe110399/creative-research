"""Offline raw scrape enrichment into source-linked caption, hashtag and sound banks."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
from creative_research.production_fields import _text, _slug, _num, _clean_copy, _pct

def enrich_production_kit_from_raw(
    kit: dict[str, Any],
    raw_root: Path,
    *,
    evidence_posts: list[dict[str, Any]] | None = None,
    max_files: int = 300,
    max_rows: int = 200_000,
) -> dict[str, Any]:
    """Recover the observed operator's FULL music/caption/hashtag library.

    All values are from local public scrape metadata, not guesses. A sound ID
    or photograph does NOT imply permission to use it in a new publication.
    """
    if not raw_root.is_dir():
        raise ValueError(f"raw_root does not exist: {raw_root}")
    chosen_by_key: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for recipe in kit["recipes"]:
        for post in recipe["observed_source_posts"]:
            key = (_text(post.get("account")).casefold(), _text(post.get("post_id")))
            chosen_by_key[key] = (recipe["recipe_id"], post)

    # If canonical evidence is available, collect sound/caption metadata
    # across ALL observed posts, not just hand-picked high-view recipes.
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for p in evidence_posts or []:
        key = (_text(p.get("account")).casefold(), _text(p.get("post_id")))
        if all(key):
            expected[key] = {
                "post_uid": _text(p.get("post_uid")),
                "post_url": _text(p.get("url")),
                "account": _text(p.get("account")),
                "account_relative_views_percentile": _pct(p),
            }
    for key, (_, source) in chosen_by_key.items():
        expected.setdefault(key, {
            "post_uid": _text(source.get("post_uid")),
            "post_url": _text(source.get("url")),
            "account": _text(source.get("account")),
            "account_relative_views_percentile": _num(
                source.get("account_relative_views_percentile")
            ),
        })

    located: dict[tuple[str, str], dict[str, Any]] = {}
    available_files = sorted({
        *raw_root.rglob("all_items.jsonl"),
        *raw_root.rglob("posts.jsonl"),
    })
    files = available_files[:max_files]
    scanned = 0
    for path in files:
        if scanned >= max_rows or len(located) == len(expected):
            break
        try:
            stream = path.open("r", encoding="utf-8-sig")
        except OSError:
            continue
        with stream:
            for line in stream:
                if scanned >= max_rows or len(located) == len(expected):
                    break
                if not line.strip():
                    continue
                scanned += 1
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(raw, dict):
                    continue
                pid = _text(
                    raw.get("post_id") or raw.get("id") or raw.get("idStr")
                    or raw.get("postId") or raw.get("awemeId")
                )
                author = raw.get("authorMeta") or raw.get("author") or {}
                if not isinstance(author, dict):
                    author = {}
                handle = _text(
                    raw.get("input") or raw.get("account")
                    or author.get("name") or author.get("uniqueId")
                ).casefold().lstrip("@").split("?")[0].split("/")[-1]
                key = (handle, pid)
                if key not in expected or key in located:
                    continue
                music = raw.get("musicMeta") or raw.get("music") or {}
                if not isinstance(music, dict):
                    music = {}
                hashtags = raw.get("hashtags") or []
                if isinstance(hashtags, str):
                    hashtags = [part for part in re.split(r"[,| ]+", hashtags) if part]
                clean_tags: list[str] = []
                if isinstance(hashtags, list):
                    for tag in hashtags[:30]:
                        name = (
                            tag.get("name") or tag.get("hashtagName")
                            if isinstance(tag, dict) else str(tag)
                        )
                        if name:
                            clean_tags.append(str(name).lstrip("#")[:60])
                located[key] = {
                    **expected[key],
                    "caption": _clean_copy(
                        raw.get("text") or raw.get("caption") or raw.get("desc"),
                        600,
                    ),
                    "hashtags": list(dict.fromkeys(clean_tags)),
                    "music_id": _text(
                        music.get("musicId") or music.get("id")
                        or raw.get("music_id")
                    ),
                    "music_name": _text(
                        music.get("musicName") or music.get("title")
                        or raw.get("music_name")
                    ),
                    "music_author": _text(
                        music.get("musicAuthor") or music.get("authorName")
                        or raw.get("music_author")
                    ),
                }

    sound_index: dict[str, dict[str, Any]] = {}
    hashtag_index: dict[str, dict[str, Any]] = {}
    caption_examples: list[dict[str, Any]] = []
    for key, meta in located.items():
        if key in chosen_by_key:
            _, source = chosen_by_key[key]
            source["observed_caption_reference_only"] = meta["caption"]
            source["observed_hashtags_reference_only"] = meta["hashtags"]
        if meta["caption"]:
            caption_examples.append({
                "post_uid": meta["post_uid"],
                "account": meta["account"],
                "url": meta["post_url"],
                "caption_reference_only": meta["caption"],
                "views_percentile_account": meta["account_relative_views_percentile"],
                "rights_scope": "research_reference_not_republication_permission",
            })
        for hashtag in meta["hashtags"]:
            hkey = hashtag.casefold()
            item = hashtag_index.setdefault(hkey, {
                "hashtag": hashtag,
                "observed_post_count": 0,
                "example_post_uids": [],
                "usage_not_recommended_without_relevance_check": True,
            })
            item["observed_post_count"] += 1
            if len(item["example_post_uids"]) < 5:
                item["example_post_uids"].append(meta["post_uid"])
        if not (meta["music_id"] or meta["music_name"]):
            continue
        sound_key = meta["music_id"] or (
            "name:"+_slug(meta["music_name"])+":"+_slug(meta["music_author"])
        )
        sound = sound_index.setdefault(sound_key, {
            "sound_key": sound_key,
            "music_id": meta["music_id"] or None,
            "music_name": meta["music_name"] or None,
            "music_author": meta["music_author"] or None,
            "source_post_uids": [],
            "source_urls": [],
            "observed_post_count": 0,
            "license_status": "not_verified",
            "rights_scope": "reference_only",
            "usable_as_commercial_sound": False,
            "source": "raw_scrape_metadata",
        })
        sound["observed_post_count"] += 1
        if len(sound["source_post_uids"]) < 25:
            sound["source_post_uids"].append(meta["post_uid"])
            sound["source_urls"].append(meta["post_url"])
        if key in chosen_by_key:
            rid, source = chosen_by_key[key]
            if source["post_uid"] == kit["recipes"][int(rid[4:])-1]["evidence"]["selected_representative_uid"]:
                for asset in kit["asset_bank"]:
                    if asset["recipe_id"] == rid and asset["kind"] == "music":
                        asset["observed_sound_key"] = sound_key
                        asset["production_status"] = "sound_found_but_license_not_verified"

    kit["music_bank"] = sorted(
        sound_index.values(),
        key=lambda s: (-s["observed_post_count"],s["sound_key"]),
    )
    kit["caption_bank"] = sorted(
        caption_examples,
        key=lambda p: (-(p["views_percentile_account"] or 0),p["post_uid"]),
    )[:250]
    kit["hashtag_bank"] = sorted(
        hashtag_index.values(),
        key=lambda h: (-h["observed_post_count"],h["hashtag"].casefold()),
    )[:500]
    q = kit["quality"]
    q["raw_enrichment"] = "scanned_public_local_archive"
    q["raw_files_scanned"] = len(files)
    q["raw_file_candidates"] = len(available_files)
    q["raw_rows_scanned"] = scanned
    q["raw_scan_may_be_truncated"] = (
        len(available_files) > max_files
        or (scanned >= max_rows and len(located) < len(expected))
    )
    q["raw_posts_matched"] = len(located)
    q["raw_posts_expected"] = len(expected)
    q["observed_caption_count"] = len(caption_examples)
    q["observed_hashtag_types"] = len(kit["hashtag_bank"])
    q["observed_sound_post_count"] = sum(
        s["observed_post_count"] for s in kit["music_bank"]
    )
    q["sound_metadata_coverage"] = round(
        q["observed_sound_post_count"] / len(expected),4
    ) if expected else 0
    return kit


