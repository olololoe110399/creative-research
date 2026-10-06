from __future__ import annotations

from importlib import resources
from pathlib import Path

STATIC_FILES = ("index.html", "app.js", "style.css", "favicon.svg")
REQUIRED_DATA_FILES = (
    "overview.json",
    "accounts.json",
    "timeline.json",
    "dimensions.json",
    "posts.json",
)


def sync_showcase_site(out_dir: Path) -> list[str]:
    """Copy the packaged showcase UI into a generated showcase directory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    static_root = resources.files("creative_research").joinpath("showcase_static")
    written: list[str] = []
    for name in STATIC_FILES:
        source = static_root.joinpath(name)
        target = out_dir / name
        target.write_bytes(source.read_bytes())
        written.append(name)
    return written


def validate_showcase_dir(root: Path) -> list[str]:
    """Return missing required static/data files for a runnable showcase."""
    required = (*STATIC_FILES, *REQUIRED_DATA_FILES)
    return [name for name in required if not (root / name).is_file()]
