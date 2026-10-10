from __future__ import annotations

import os
import re
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


def confined_path(directory: Path, *components: str) -> Path:
    """Keep imported identifiers and existing symlinks inside an output directory."""
    for component in components:
        if component in {".", ".."} or not re.fullmatch(r"[a-zA-Z0-9_.@-]+", component):
            raise ValueError("unsafe_path_component")
    root = directory.resolve()
    path = root.joinpath(*components).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path_outside_output")
    return path
