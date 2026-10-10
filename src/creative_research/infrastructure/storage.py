"""Atomic file writes and recoverable directory replacement, not stage transactions."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    import pandas as pd


@contextmanager
def atomic_output(path: Path, *, mode: int | None = None) -> Iterator[Path]:
    """Stage beside the destination, fsync, then replace; retain old output on failure."""
    path = path.absolute()
    path = path.parent.resolve() / path.name  # Replace a leaf symlink, never its external target.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        permissions = (
            mode if mode is not None else (path.stat().st_mode & 0o777 if path.is_file() else 0o644)
        )
        os.fchmod(fd, permissions)
        os.close(fd)
        fd = -1
        yield temporary
        temporary.chmod(permissions)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    with atomic_output(path, mode=mode) as temporary:
        temporary.write_text(text, encoding="utf-8")


def write_bytes(path: Path, payload: bytes) -> None:
    with atomic_output(path) as temporary:
        temporary.write_bytes(payload)


@contextmanager
def replace_directory(path: Path) -> Iterator[Path]:
    """Stage a complete tree; retain a backup and roll back publication errors.

    Two renames are not crash-atomic. Callers must run one writer and preserve backups.
    """
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(f"Expected a regular output directory: {path}")
    path = path.absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{path.name}-", dir=path.parent) as temporary:
        staged = Path(temporary) / "content"
        staged.mkdir()
        yield staged
        backup = (
            path.with_name(f".{path.name}.backup-{uuid4().hex[:12]}") if path.exists() else None
        )
        if backup is not None:
            path.replace(backup)
        try:
            staged.replace(path)
        except BaseException:
            if backup is not None:
                backup.replace(path)
            raise
        if backup is not None:
            logging.getLogger(__name__).warning(
                "previous_directory_retained", extra={"context": {"backup": str(backup)}}
            )


def write_json(path: Path, payload: Any, *, mode: int | None = None) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str), mode=mode)


def read_json_object(
    path: Path, *, missing_ok: bool = False, tolerate_invalid: bool = False
) -> dict[str, Any]:
    """Read object metadata with explicit recovery; never hide permission/IO failures."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
    except FileNotFoundError:
        if not missing_ok:
            raise
        return {}
    except ValueError as exc:
        if not tolerate_invalid:
            raise ValueError(f"Invalid JSON object: {path}") from exc
        logging.getLogger(__name__).warning(
            "invalid_json_metadata", extra={"context": {"path": str(path)}}
        )
        return {}
    return payload


def write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with atomic_output(path) as temporary:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_jsonl(
    path: Path, *, missing_ok: bool = False, tolerate_invalid: bool = False
) -> list[dict[str, Any]]:
    """Read object records; only explicitly resumable inputs may skip invalid rows."""
    if missing_ok and not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("Expected a JSON object")
            except ValueError as exc:
                if not tolerate_invalid:
                    raise ValueError(f"Invalid JSONL object at {path}:{line_number}") from exc
                logging.getLogger(__name__).warning(
                    "invalid_jsonl_row", extra={"context": {"path": str(path), "line": line_number}}
                )
                continue
            rows.append(row)
    return rows


def file_sha1(path: Path) -> str:
    """Content fingerprint for cache identity only, not security verification."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha1").hexdigest()


def append_jsonl(path: Path, row: Any) -> None:
    append_jsonl_rows(path, [row])


def append_jsonl_rows(path: Path, rows: Iterable[Any]) -> None:
    """Checkpoint a batch with one flush; readers should tolerate a partial final line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_parquet(path: Path, frame: pd.DataFrame) -> None:
    with atomic_output(path) as temporary:
        frame.to_parquet(temporary, index=False)


def write_csv(path: Path, frame: pd.DataFrame, **options: Any) -> None:
    options.setdefault("index", False)
    with atomic_output(path) as temporary:
        frame.to_csv(temporary, **options)


def read_table(path: Path) -> pd.DataFrame:
    import pandas as pd

    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported table format: {path}")
