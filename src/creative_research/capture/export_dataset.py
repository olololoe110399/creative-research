"""Portable, read-only-source handoff of selected crawl records and archived media."""

from __future__ import annotations

import csv
import hashlib
import mimetypes
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from creative_research.capture.cache import sha256, source_fingerprint
from creative_research.capture.contracts import DATASET_EXPORT_SCHEMA_VERSION
from creative_research.capture.normalization import normalize_post
from creative_research.capture.validation import validate_dataset
from creative_research.identity import clean_account_handle, stable_account_id, stable_post_id
from creative_research.infrastructure.locking import project_writer
from creative_research.infrastructure.paths import confined_path, project_root, resolve_path
from creative_research.infrastructure.storage import (
    atomic_output,
    read_json_object,
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
CSV_FIELDS = (
    "post_uid",
    "account_id",
    "platform",
    "account",
    "post_id",
    "content_type",
    "url",
    "caption",
    "created_at",
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "expected_slide_count",
    "available_slide_count",
    "video_count",
    "media_status",
)
CHUNK_BYTES = 1024 * 1024


def _signature(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _confine(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Source path escapes its declared root: {path}")
    return path


def _account(record: dict[str, Any], fallback: str = "") -> str:
    author = record.get("authorMeta") or record.get("author") or {}
    values = [record.get("account"), record.get("input")]
    if isinstance(author, dict):
        values.extend(author.get(key) for key in ("name", "uniqueId", "unique_id"))
    return next((clean_account_handle(value) for value in values if value), fallback)


def _post_id(record: dict[str, Any]) -> str:
    for key in ("post_id", "id", "idStr", "postId", "awemeId", "aweme_id"):
        if record.get(key) is not None and str(record[key]).strip():
            return str(record[key]).strip()
    for key in ("url", "webVideoUrl", "postUrl"):
        match = re.search(r"/(?:video|photo)/(\d+)", str(record.get(key) or ""))
        if match:
            return match.group(1)
    raise ValueError("Selected record has no post identifier")


def _key(record: dict[str, Any], fallback: str = "") -> tuple[str, str]:
    account = _account(record, fallback)
    if not account or account.casefold() == "unknown":
        raise ValueError("Selected record has no account identifier")
    return account.casefold(), _post_id(record)


class _Sources:
    """Track source stability and hash/copy binaries without loading them into memory."""

    def __init__(self) -> None:
        self.signatures: dict[Path, tuple[int, int, int, int]] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.files: dict[str, Path] = {}
        self.cached: dict[Path, str | None] = {}
        self.roles: dict[str, set[Path]] = {}
        self.absent_directories: set[Path] = set()
        self.verified_files: dict[Path, dict[str, Any]] | None = None

    def track(self, path: Path) -> None:
        signature = _signature(path)
        if path in self.signatures and signature != self.signatures[path]:
            raise ValueError(f"Source changed during export: {path}")
        self.signatures[path] = signature

    def directory(self, root: Path, path: Path) -> None:
        _confine(root, path)
        if not path.exists():
            self.absent_directories.add(path)
        elif not path.is_dir():
            raise ValueError(f"Expected a source directory: {path}")
        else:
            self.track(path)

    def records(self, root: Path, path: Path) -> list[dict[str, Any]]:
        _confine(root, path)
        self.track(path)
        rows = read_jsonl(path)
        self.track(path)
        return rows

    def add(self, root: Path, path: Path, role: str, label: str) -> str | None:
        _confine(root, path)
        if not path.is_file():
            raise ValueError(f"Expected a regular media file: {path}")
        self.track(path)
        if self.verified_files is not None:
            record = self.verified_files[path.resolve()]
            if record.get("sha256") != sha256(path) or record.get("bytes") != path.stat().st_size:
                raise ValueError(f"Verified media changed before export: {path}")
        self.roles.setdefault(role, set()).add(path)
        if path in self.cached:
            return self.cached[path]
        if path.stat().st_size == 0:
            self.cached[path] = None
            return None
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        self.track(path)
        asset_id = f"sha256:{digest}"
        source_path = f"{label}/{path.relative_to(root).as_posix()}"
        if asset_id not in self.assets:
            media_type = "video" if path.suffix.lower() in VIDEO_EXTS else "image"
            ext = path.suffix.lower().replace(".jpeg", ".jpg")
            directory = "videos" if media_type == "video" else "images"
            self.assets[asset_id] = {
                "asset_id": asset_id,
                "path": f"assets/{directory}/{digest}{ext}",
                "media_type": media_type,
                "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "bytes": path.stat().st_size,
                "sha256": digest,
                "source_paths": [],
            }
            self.files[asset_id] = path
        if source_path not in self.assets[asset_id]["source_paths"]:
            self.assets[asset_id]["source_paths"].append(source_path)
        self.cached[path] = asset_id
        return asset_id

    def verify(self) -> None:
        for path in self.absent_directories:
            if path.exists() or path.is_symlink():
                raise ValueError(f"Source appeared during export: {path}")
        for path, signature in self.signatures.items():
            if _signature(path) != signature:
                raise ValueError(f"Source changed during export: {path}")

    def copy(self, staged: Path) -> None:
        for asset_id, source in self.files.items():
            asset = self.assets[asset_id]
            target = staged / asset["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with atomic_output(target) as temporary:
                with source.open("rb") as reader, temporary.open("wb") as writer:
                    while chunk := reader.read(CHUNK_BYTES):
                        writer.write(chunk)
                        digest.update(chunk)
                if (
                    digest.hexdigest() != asset["sha256"]
                    or temporary.stat().st_size != asset["bytes"]
                ):
                    raise ValueError(f"Source changed while copying: {source}")


def _load_posts(selected: Path, sources: _Sources) -> tuple[list[dict[str, Any]], int]:
    posts_dir = _confine(selected, selected / "posts")
    sources.directory(selected, selected)
    sources.directory(selected, posts_dir)
    sources.directory(selected, selected / "normalized")
    paths = sorted(posts_dir.glob("*.jsonl"))
    if not paths:
        raise ValueError(f"No selected posts/*.jsonl files: {selected}")
    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    normalized_path = selected / "normalized/posts.jsonl"
    if normalized_path.exists() or normalized_path.is_symlink():
        for record in sources.records(selected, normalized_path):
            key = _key(record)
            if key in normalized and normalized[key] != record:
                raise ValueError(f"Conflicting normalized selected records: {key}")
            normalized[key] = record
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_rows = 0
    for path in paths:
        for line_number, raw in enumerate(sources.records(selected, path), 1):
            key = _key(raw, path.stem)
            if key in unique:
                if unique[key]["raw"] != raw:
                    raise ValueError(f"Conflicting selected payloads: {key} at {path}")
                duplicate_rows += 1
                continue
            metadata = dict(normalized.get(key) or normalize_post(raw))
            account = _account(metadata) or _account(raw, path.stem)
            if account.casefold() == "unknown":
                account = _account(raw, path.stem)
            metadata.update(account=account, post_id=key[1])
            # Match the engine's existing IDs, including its display-account casing.
            unique[key] = {
                "post_uid": stable_post_id(account, key[1]),
                "account_id": stable_account_id(account),
                "platform": "tiktok",
                "account": account,
                "post_id": key[1],
                "content_type": "slideshow"
                if raw.get("isSlideshow", bool(raw.get("slideshowImageLinks")))
                else "video",
                "metadata": metadata,
                "raw": raw,
                "source": {
                    "root": "selected",
                    "file": path.relative_to(selected).as_posix(),
                    "record": line_number,
                },
            }
    if not unique:
        raise ValueError("Selected dataset is empty")
    if len({post["post_uid"] for post in unique.values()}) != len(unique):
        raise ValueError("Export post_uid collision")
    return [unique[key] for key in sorted(unique)], duplicate_rows


def _account_dir(root: Path, account: str) -> Path:
    direct = confined_path(root, account)
    if direct.exists() or not root.exists():
        return direct
    matches = [path for path in root.iterdir() if path.name.casefold() == account.casefold()]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous media account directory: {account}")
    return _confine(root, matches[0]) if matches else direct


def _media_files(
    root: Path,
    directory: Path,
    extensions: set[str],
    sources: _Sources,
) -> list[Path]:
    sources.directory(root, directory)
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in extensions
        and (sources.verified_files is None or path.resolve() in sources.verified_files)
    )


def _attach_media(
    post: dict[str, Any],
    media_root: Path,
    sources: _Sources,
) -> list[dict[str, Any]]:
    account, post_id = post["account"], post["post_id"]
    account_dir = _account_dir(media_root, account)
    directory = confined_path(account_dir, post_id)
    images = _media_files(media_root, directory, IMAGE_EXTS, sources)
    media: dict[str, Any] = {"covers": [], "avatars": [], "slides": [], "videos": []}
    post_missing: list[dict[str, Any]] = []

    def unavailable(kind: str, index: int | None = None, reason: str = "not_found") -> None:
        post_missing.append(
            {
                "post_uid": post["post_uid"],
                "account": account,
                "post_id": post_id,
                "kind": kind,
                "index": index,
                "reason": reason,
            }
        )

    def add(path: Path, kind: str, root: Path, label: str, index: int | None = None) -> None:
        asset_id = sources.add(root, path, kind, label)
        if asset_id is None:
            unavailable(kind, index, "empty_file")
        elif kind == "slide":
            media["slides"].append({"index": index, "asset_id": asset_id})
        else:
            media[{"cover": "covers", "avatar": "avatars", "video": "videos"}[kind]].append(
                asset_id
            )

    for path in images:
        if path.stem == "cover":
            add(path, "cover", media_root, "media")
        elif path.stem.startswith("slide_"):
            match = re.fullmatch(r"slide_(\d+)", path.stem)
            if not match or int(match[1]) < 1:
                raise ValueError(f"Invalid slide filename: {path}")
            add(path, "slide", media_root, "media", int(match[1]))
        else:
            raise ValueError(f"Unrecognized post image: {path}")
    if not any(path.stem == "cover" for path in images):
        unavailable("cover")
    avatars = _media_files(media_root, confined_path(account_dir, "profile"), IMAGE_EXTS, sources)
    for path in avatars:
        add(path, "avatar", media_root, "media")
    author = post["raw"].get("authorMeta") or {}
    if (
        not avatars
        and isinstance(author, dict)
        and any(author.get(key) for key in ("avatar", "originalAvatarUrl"))
    ):
        unavailable("avatar")
    videos = _media_files(media_root, directory, VIDEO_EXTS, sources)
    for path in videos:
        add(path, "video", media_root, "media")
    if post["content_type"] == "video" and not videos:
        unavailable("video")
    expected = len(post["raw"].get("slideshowImageLinks") or [])
    positions = {slide["index"] for slide in media["slides"]}
    if len(positions) != len(media["slides"]):
        raise ValueError(f"Ambiguous slide positions for @{account}/{post_id}")
    already_missing = {item["index"] for item in post_missing if item["kind"] == "slide"}
    if post["content_type"] == "slideshow":
        for index in sorted(set(range(1, expected + 1)) - positions - already_missing):
            unavailable("slide", index)
        if not expected and not positions:
            unavailable("slide", reason="no_slide_inventory")
    media["slides"].sort(key=lambda item: (item["index"], item["asset_id"]))
    for key in ("covers", "avatars", "videos"):
        media[key] = sorted(set(media[key]))
    post.update(
        media=media,
        expected_slide_count=expected,
        available_slide_count=len(positions),
        media_status="incomplete" if post_missing else "complete",
    )
    return post_missing


def _destination(out: str, roots: list[Path], include_zip: bool) -> tuple[Path, Path]:
    requested = Path(out).expanduser()
    if not requested.is_absolute():
        requested = project_root() / requested
    if any(path.is_symlink() for path in (requested, *requested.parents)):
        raise ValueError("Output must not traverse symlinks")
    destination = resolve_path(out)
    archive = destination.with_name(destination.name + ".zip")
    for path in [destination, *([archive] if include_zip else [])]:
        if path.exists() or path.is_symlink():
            raise ValueError(f"Output already exists: {path}")
        if any(path.is_relative_to(root) or root.is_relative_to(path) for root in roots):
            raise ValueError(f"Output overlaps a source tree: {path}")
    return destination, archive


def _write_csv(path: Path, posts: list[dict[str, Any]]) -> None:
    with (
        atomic_output(path) as temporary,
        temporary.open("w", encoding="utf-8-sig", newline="") as stream,
    ):
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for post in posts:
            row = {field: post.get(field, post["metadata"].get(field)) for field in CSV_FIELDS}
            row["video_count"] = len(post["media"]["videos"])
            writer.writerow(row)


def _checksums(staged: Path, assets: list[dict[str, Any]]) -> None:
    hashes = {asset["path"]: asset["sha256"] for asset in assets}
    for path in sorted(staged.iterdir()):
        if path.is_file():
            with path.open("rb") as stream:
                hashes[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    write_text(
        staged / "checksums.sha256",
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
    )


def _write_zip(path: Path, staged: Path, name: str) -> None:
    with (
        atomic_output(path) as temporary,
        zipfile.ZipFile(temporary, "w", allowZip64=True) as archive,
    ):
        for source in sorted(staged.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(staged)
            info = zipfile.ZipInfo.from_file(source, f"{name}/{relative.as_posix()}")
            info.compress_type = (
                zipfile.ZIP_STORED if relative.parts[0] == "assets" else (zipfile.ZIP_DEFLATED)
            )
            with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
                shutil.copyfileobj(reader, writer, CHUNK_BYTES)


README = """# Selected TikTok dataset handoff

This offline export contains the currently selected snapshot of each post and the
local image/video bytes. manifest.capture records the originating crawl run when
available; standalone inputs may have no run metadata. It contains no crawl
history, generated analysis or private operating state. Original remote media URLs
can expire; use the packaged assets.

## Read the data

`posts.jsonl` has one UTF-8 JSON object per unique (platform, case-folded account,
post_id). IDs in the export envelope are strings. `metadata` preserves the selected
normalized record (or is normalized from raw when unavailable); `raw` preserves all
fields and original types of the selected crawl payload. `source.file` is relative
to the original selected input, and `source.record` is its 1-based nonblank record
number. The input labels in manifest.json are informational, not dependencies.

`media.covers`, `media.avatars` and `media.videos` are arrays of asset IDs.
`media.slides` contains {index, asset_id}, ordered by the original 1-based slide
position. Repeated images still retain all positions. Join asset_id to assets.jsonl
and resolve its `path` relative to this folder, on any machine. SHA-256-identical
files share one asset; distinct bytes remain distinct assets. `source_paths` in
assets.jsonl are relative to the labeled media input root.

`posts.csv` is a UTF-8 BOM convenience table, not the complete payload. Import ID
columns as text in spreadsheet software to avoid rounding long TikTok IDs.
`missing_assets.jsonl` reports absent/empty assets; affected posts remain exported
with media_status=incomplete. Identical duplicate selected rows are collapsed;
conflicting payloads fail export instead of guessing which snapshot to select.

## Check completeness

`manifest.completion.capture` is true for acquisition without recorded failures,
false for incomplete acquisition, or null when capture provenance is unavailable.
`manifest.completion.media` is true when no required assets are inventoried as
missing. `manifest.completion.complete` requires both to be true. A valid package
can therefore be partial or have unknown acquisition completeness. Keep incomplete
posts and their missing_assets entries when importing.

Capture completion describes the requested sample and filters, not exhaustive
account history. Raw provider error logs remain in the producer's capture archive;
the export contains valid post records and records error counts in manifest.capture.
Integrity/completeness checks do not prove source metadata accuracy, successful
media decoding, analytical quality or media rights.

## Verify the package

On macOS: `shasum -a 256 -c checksums.sha256`
On Linux: `sha256sum -c checksums.sha256`

Checksums cover every exported file except checksums.sha256 itself. The ZIP contains
this same folder and uses ZIP64 with uncompressed image/video entries. Extraction
does not require the source project or creative-research engine.

Only one writer may export to a destination. Existing outputs are never replaced.
The folder and ZIP are staged before publication; caught failures roll back newly
published outputs. Publishing two paths is not a crash-atomic transaction.
"""


def run(
    *,
    input_dir: str,
    media_root: str = "data/media",
    out: str,
    include_zip: bool = False,
    dry_run: bool = False,
    require_verified_media: bool = False,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "input_dir": input_dir,
        "media_root": media_root,
        "out": out,
        "include_zip": include_zip,
        "dry_run": dry_run,
        "require_verified_media": require_verified_media,
        "lineage": lineage,
    }
    if dry_run:
        return _run(**values)
    with project_writer():
        return _run(**values)


def _run(
    *,
    input_dir: str,
    media_root: str,
    out: str,
    include_zip: bool,
    dry_run: bool,
    require_verified_media: bool,
    lineage: dict[str, Any] | None,
) -> dict[str, Any]:
    selected, media = map(resolve_path, (input_dir, media_root))
    destination, archive = _destination(out, [selected, media], include_zip)
    sources = _Sources()
    if require_verified_media:
        report_path = media / "download_report.json"
        report = read_json_object(report_path)
        if report.get("source_fingerprint") != source_fingerprint(selected):
            raise ValueError("Media archive belongs to a different capture snapshot")
        sources.track(report_path)
        sources.verified_files = {}
        for name, record in report["assets"].items():
            path = media / name
            _confine(media, path)
            if path.is_symlink() or not path.is_file():
                raise ValueError("Verified media inventory contains a missing/unsafe file")
            sources.verified_files[path.resolve()] = record
    sources.directory(media, media)
    posts, duplicates = _load_posts(selected, sources)
    missing = [item for post in posts for item in _attach_media(post, media, sources)]
    assets = [sources.assets[key] for key in sorted(sources.assets)]
    sources.verify()
    capture: dict[str, Any] | None = None
    run_info = selected / "run_info.json"
    if run_info.exists():
        sources.track(_confine(selected, run_info))
        info = read_json_object(run_info)
        capture = {
            key: info.get(key)
            for key in ("actor", "started_at", "finished_at", "accounts", "settings")
        }
        capture["batches"] = [
            {
                key: batch.get(key)
                for key in (
                    "batch_index",
                    "profiles",
                    "run_id",
                    "dataset_id",
                    "status",
                    "started_at",
                    "finished_at",
                )
            }
            for batch in info.get("batches", [])
        ]
        capture["complete"] = bool(
            info.get("finished_at")
            and not info.get("manifest", {}).get("failed_batches")
            and not info.get("manifest", {}).get("interrupted")
            and not info.get("manifest", {}).get("error_records")
            and all(batch.get("status") == "SUCCEEDED" for batch in info.get("batches", []))
        )
        capture["error_records"] = info.get("manifest", {}).get("error_records", 0)
    manifest = {
        "schema_version": DATASET_EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "snapshot": "selected_only",
        "capture": capture,
        "includes_history": False,
        "includes_analysis": False,
        "completion": {
            "capture": capture["complete"] if capture else None,
            "media": not missing,
            "complete": bool(capture and capture["complete"] and not missing),
        },
        "pipeline": lineage,
        "sources": {
            label: root.relative_to(project_root()).as_posix()
            if root.is_relative_to(project_root())
            else f"{label}:{root.name}"
            for label, root in (("selected", selected), ("media", media))
        },
        "counts": {
            "posts": len(posts),
            "accounts": len({post["account_id"] for post in posts}),
            "content_types": dict(Counter(post["content_type"] for post in posts)),
            "duplicate_post_rows_removed": duplicates,
            "source_media_files": len(sources.cached),
            "empty_media_files": sum(value is None for value in sources.cached.values()),
            "source_media_by_role": {
                kind: len(paths) for kind, paths in sorted(sources.roles.items())
            },
            "unique_assets": len(assets),
            "unique_assets_by_type": dict(Counter(asset["media_type"] for asset in assets)),
            "asset_bytes": sum(asset["bytes"] for asset in assets),
            "missing_assets": len(missing),
            "posts_with_missing_assets": len({item["post_uid"] for item in missing}),
        },
    }
    result = {
        "dry_run": dry_run,
        "output": str(destination),
        "zip": str(archive) if include_zip else None,
        **manifest,
    }
    if dry_run:
        return result
    destination.parent.mkdir(parents=True, exist_ok=True)
    published = False
    zip_published = False
    with tempfile.TemporaryDirectory(prefix=".dataset-export-", dir=destination.parent) as temp:
        staged = Path(temp) / "dataset"
        staged.mkdir()
        (staged / "assets/images").mkdir(parents=True)
        (staged / "assets/videos").mkdir()
        staged_zip = Path(temp) / "dataset.zip"
        try:
            sources.copy(staged)
            write_jsonl(staged / "posts.jsonl", posts)
            _write_csv(staged / "posts.csv", posts)
            write_jsonl(staged / "assets.jsonl", assets)
            write_jsonl(staged / "missing_assets.jsonl", missing)
            write_json(staged / "manifest.json", manifest)
            write_text(staged / "README.md", README)
            _checksums(staged, assets)
            validation = validate_dataset(staged)
            if not validation["ok"]:
                raise ValueError(f"Dataset validation failed: {validation['issues']}")
            result["validation"] = validation
            if include_zip:
                _write_zip(staged_zip, staged, destination.name)
            sources.verify()
            _destination(out, [selected, media], include_zip)
            staged.replace(destination)
            published = True
            if include_zip:
                staged_zip.replace(archive)
                zip_published = True
        except BaseException:
            if zip_published:
                archive.unlink()
            if published:
                shutil.rmtree(destination)
            raise
    return result


def ensure_zip(dataset: Path) -> Path:
    """Recover a missing ZIP and verify an existing ZIP against the published folder."""
    archive = dataset.with_name(dataset.name + ".zip")
    if archive.is_symlink():
        raise ValueError("Dataset ZIP must not be a symlink")
    if not archive.exists():
        with atomic_output(archive) as temporary:
            _write_zip(temporary, dataset, dataset.name)
    expected = {
        path.relative_to(dataset).as_posix(): path for path in dataset.rglob("*") if path.is_file()
    }
    with zipfile.ZipFile(archive) as packaged:
        members = [member for member in packaged.infolist() if not member.is_dir()]
        if len(members) != len(expected) or {member.filename for member in members} != {
            f"{dataset.name}/{name}" for name in expected
        }:
            raise ValueError("ZIP inventory differs from published dataset")
        for name, path in expected.items():
            with packaged.open(f"{dataset.name}/{name}") as handle:
                digest = hashlib.sha256()
                while chunk := handle.read(CHUNK_BYTES):
                    digest.update(chunk)
                if digest.hexdigest() != sha256(path):
                    raise ValueError(f"ZIP checksum differs from published dataset: {name}")
    return archive
