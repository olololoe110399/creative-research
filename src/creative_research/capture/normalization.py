"""Normalize source metadata without provider imports or inferred metrics."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from creative_research.identity import clean_account_handle


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
