from __future__ import annotations

from pathlib import Path

from creative_research.showcase_site import (
    REQUIRED_DATA_FILES,
    STATIC_FILES,
    sync_showcase_site,
    validate_showcase_dir,
)
from creative_research.stages.showcase import build_parser, resolve_showcase_dir


def test_sync_showcase_site_writes_packaged_template(tmp_path: Path) -> None:
    written = sync_showcase_site(tmp_path)
    assert set(written) == set(STATIC_FILES)
    for name in STATIC_FILES:
        assert (tmp_path / name).is_file()

    assert "Creative Evidence" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Promise.all" in (tmp_path / "app.js").read_text(encoding="utf-8")


def test_validate_showcase_dir_requires_static_and_data(tmp_path: Path) -> None:
    sync_showcase_site(tmp_path)
    missing = validate_showcase_dir(tmp_path)
    assert set(missing) == set(REQUIRED_DATA_FILES)

    for name in REQUIRED_DATA_FILES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert validate_showcase_dir(tmp_path) == []


def test_showcase_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.dir == "data/06_showcase"
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.open_browser is False


def test_resolve_showcase_dir_uses_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    assert resolve_showcase_dir("data/06_showcase") == (
        tmp_path / "data/06_showcase"
    ).resolve()
