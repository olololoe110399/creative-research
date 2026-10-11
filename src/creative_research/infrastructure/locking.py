"""Nonblocking, process-safe project writer lock with same-thread nesting."""

from __future__ import annotations

import importlib
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from creative_research.errors import ApplicationError
from creative_research.infrastructure.paths import project_root

_GUARD = threading.Lock()
_OWNERS: dict[Path, int] = {}


@contextmanager
def project_writer() -> Iterator[None]:
    path = project_root() / ".capture.lock"
    owner = threading.get_ident()
    with _GUARD:
        nested = _OWNERS.get(path) == owner
        if path in _OWNERS and not nested:
            raise ApplicationError("Another writer is active in this project")
        if not nested:
            _OWNERS[path] = owner
    if nested:
        yield
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError("Writer lock must not be a symlink")
        with path.open("a+b") as handle:
            try:
                if os.name == "nt":
                    msvcrt = importlib.import_module("msvcrt")

                    handle.write(b"0")
                    handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ApplicationError("Another writer is active in this project") from exc
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        with _GUARD:
            _OWNERS.pop(path, None)
