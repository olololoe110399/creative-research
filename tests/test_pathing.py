from __future__ import annotations

from pathlib import Path

from creative_research.pathing import portable_path, resolve_path


def test_portable_path_inside_project_is_relative(tmp_path: Path) -> None:
    target = tmp_path / "data" / "x"
    target.mkdir(parents=True)
    assert portable_path(target, tmp_path) == "data/x"


def test_resolve_path_uses_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    assert resolve_path("data/file.json") == (tmp_path / "data/file.json").resolve()
