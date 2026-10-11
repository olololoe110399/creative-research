"""Bind archived bytes to source records; never trust a nonempty file alone."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from creative_research.infrastructure.storage import read_json_object, write_json


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_fingerprint(root: Path) -> str:
    paths = sorted((root / "posts").glob("*.jsonl"))
    if not paths:
        raise ValueError("Capture contains no post files")
    paths.extend(sorted((root / "normalized").glob("*.jsonl")))
    paths.extend(sorted((root / "profiles").glob("*.json")))
    paths.extend(path for path in (root / "run_info.json", root / "manifest.json") if path.exists())
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe capture post file")
    return fingerprint({path.relative_to(root).as_posix(): sha256(path) for path in paths})


def _attestation(path: Path) -> Path:
    return path.with_name(f".{path.name}.attestation.json")


def attest(path: Path, source: str) -> dict[str, Any]:
    record = {"source_fingerprint": source, "sha256": sha256(path), "bytes": path.stat().st_size}
    write_json(_attestation(path), record)
    return record


def verified(path: Path, source: str) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file() or not path.stat().st_size:
        return None
    record = read_json_object(_attestation(path), missing_ok=True, tolerate_invalid=True)
    if (
        record.get("source_fingerprint") != source
        or record.get("bytes") != path.stat().st_size
        or record.get("sha256") != sha256(path)
    ):
        return None
    return record
