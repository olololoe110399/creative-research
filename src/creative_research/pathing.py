from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    value = os.environ.get("CREATIVE_RESEARCH_PROJECT_ROOT")
    return Path(value).expanduser().resolve() if value else Path.cwd().resolve()


def portable_path(path: Path, base: Path | None = None) -> str:
    resolved = path.expanduser().resolve()
    root = (base or project_root()).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def resolve_path(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return ((base or project_root()) / path).resolve()
