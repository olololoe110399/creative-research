from __future__ import annotations

from pathlib import Path

import pytest

from creative_research.infrastructure.paths import confined_path, portable_path, resolve_path


def test_portable_path_inside_project_is_relative(tmp_path: Path) -> None:
    target = tmp_path / "data" / "x"
    target.mkdir(parents=True)
    assert portable_path(target, tmp_path) == "data/x"


def test_resolve_path_uses_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    assert resolve_path("data/file.json") == (tmp_path / "data/file.json").resolve()


def test_confined_path_rejects_symlinked_file_without_overwriting_it(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("keep existing content", encoding="utf-8")
    (output / "raw.json").symlink_to(outside)
    with pytest.raises(ValueError, match="path_outside_output"):
        confined_path(output, "raw.json")
    assert outside.read_text(encoding="utf-8") == "keep existing content"
