"""Read-only verification of portable dataset records, references and checksums."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

from creative_research.capture.contracts import DATASET_EXPORT_SCHEMA_VERSION, DATASET_FILES
from creative_research.infrastructure.storage import read_json_object, read_jsonl


def _file(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or relative.is_absolute()
        or any(part in {".", ".."} for part in name.split("/"))
    ):
        raise ValueError("Invalid dataset-relative path")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or unsafe dataset file: {name}")
    return path


def _validate(root: Path) -> dict[str, Any]:
    manifest = read_json_object(_file(root, "manifest.json"))
    if manifest.get("schema_version") != DATASET_EXPORT_SCHEMA_VERSION:
        raise ValueError("Unsupported dataset schema_version")
    posts = read_jsonl(_file(root, "posts.jsonl"))
    assets = read_jsonl(_file(root, "assets.jsonl"))
    missing = read_jsonl(_file(root, "missing_assets.jsonl"))
    hashes: dict[str, str] = {}
    for line in _file(root, "checksums.sha256").read_text().splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or name in hashes:
            raise ValueError("Invalid or duplicate checksum entry")
        with _file(root, name).open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        hashes[name] = digest
    asset_map: dict[str, dict[str, Any]] = {}
    for asset in assets:
        uid, asset_path = asset.get("asset_id"), asset.get("path")
        if (
            not isinstance(uid, str)
            or not uid
            or uid in asset_map
            or not isinstance(asset_path, str)
        ):
            raise ValueError("Missing or duplicate asset identity/path")
        if not asset_path.startswith("assets/") or hashes.get(asset_path) != asset.get("sha256"):
            raise ValueError("Asset checksum/path differs from inventory")
        if uid != f"sha256:{asset.get('sha256')}":
            raise ValueError("Asset identity differs from content checksum")
        if _file(root, asset_path).stat().st_size != asset.get("bytes"):
            raise ValueError("Asset byte count differs from inventory")
        asset_map[uid] = asset
    expected = DATASET_FILES | {asset["path"] for asset in assets}
    if set(hashes) != expected:
        raise ValueError("Checksum inventory differs from dataset files")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != expected | {"checksums.sha256"}:
        raise ValueError("Dataset contains missing or unlisted files")
    post_ids: set[str] = set()
    keys: set[tuple[str, str, str]] = set()
    for post in posts:
        if not all(
            isinstance(post.get(field), str) and post[field]
            for field in ("post_uid", "post_id", "account_id", "account", "platform")
        ):
            raise ValueError("Post identifiers must be nonempty strings")
        uid = post["post_uid"]
        key = post["platform"], post["account"].casefold(), post["post_id"]
        if uid in post_ids or key in keys:
            raise ValueError("Duplicate post identity")
        post_ids.add(uid)
        keys.add(key)
        if (
            post.get("content_type") not in {"video", "slideshow"}
            or not isinstance(post.get("raw"), dict)
            or not isinstance(post.get("metadata"), dict)
        ):
            raise ValueError("Invalid post content/raw/metadata")
        media = post.get("media")
        if not isinstance(media, dict) or not all(
            isinstance(media.get(kind), list) for kind in ("covers", "avatars", "videos", "slides")
        ):
            raise ValueError("Invalid post media inventory")
        indices: list[int] = []
        for slide in media["slides"]:
            if not isinstance(slide, dict):
                raise ValueError("Invalid slide record")
            index = slide.get("index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 1:
                raise ValueError("Invalid slide index")
            indices.append(index)
        if indices != sorted(set(indices)):
            raise ValueError("Slide positions must be unique, positive and ordered")
        references = [uid for kind in ("covers", "avatars", "videos") for uid in media[kind]]
        references.extend(slide.get("asset_id") for slide in media["slides"])
        if any(not isinstance(uid, str) or uid not in asset_map for uid in references):
            raise ValueError("Post references an unknown asset")
    if not posts:
        raise ValueError("Dataset is empty")
    if any(row.get("post_uid") not in post_ids for row in missing):
        raise ValueError("Missing-asset inventory references an unknown post")
    incomplete = {row["post_uid"] for row in missing}
    for post in posts:
        expected_status = "incomplete" if post["post_uid"] in incomplete else "complete"
        if post.get("media_status") != expected_status or post.get("available_slide_count") != len(
            post["media"]["slides"]
        ):
            raise ValueError("Post media status/count differs from inventory")
    counts = manifest.get("counts", {})
    if not isinstance(counts, dict):
        raise ValueError("Invalid manifest counts")
    if (
        counts.get("posts") != len(posts)
        or counts.get("unique_assets") != len(assets)
        or counts.get("missing_assets") != len(missing)
    ):
        raise ValueError("Manifest counts differ from dataset")
    completion = manifest.get("completion")
    if completion is not None:
        capture = manifest.get("capture")
        if capture is not None and not isinstance(capture, dict):
            raise ValueError("Invalid capture provenance")
        capture_complete = capture.get("complete") if capture is not None else None
        if (
            not isinstance(completion, dict)
            or not {"capture", "media", "complete"}.issubset(completion)
            or not any(capture_complete is value for value in (True, False, None))
            or completion.get("capture") is not capture_complete
            or completion.get("media") is not (not missing)
            or completion.get("complete") is not (completion.get("capture") is True and not missing)
        ):
            raise ValueError("Manifest completion differs from capture/media availability")
    return {
        "ok": True,
        "posts": len(posts),
        "assets": len(assets),
        "missing_assets": len(missing),
        "issues": [],
    }


def validate_dataset(path: Path) -> dict[str, Any]:
    """Verify integrity, allowing explicitly inventoried missing media."""
    try:
        return _validate(path.resolve())
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return {"ok": False, "issues": [str(exc)]}
