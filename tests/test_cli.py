from __future__ import annotations

import json
from pathlib import Path

from creative_research.cli import COMMANDS, cmd_init, doctor_checks, status_rows
from creative_research.constants import WORKSPACE_DIRS


def test_canonical_commands_exist() -> None:
    assert set(COMMANDS) == {
        "scrape",
        "select-accounts",
        "prepare-media",
        "manifest-slides",
        "vision-slides",
        "download-videos",
        "vision-videos",
        "build-master",
        "build-warehouse",
        "analyze-performance",
        "analyze-cadence",
        "build-families",
        "analyze-propagation",
        "rank-posts",
        "extract-references",
        "query",
        "group-references",
        "references",
    }


def test_init_creates_canonical_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    assert cmd_init() == 0
    for rel in WORKSPACE_DIRS:
        assert (tmp_path / rel).is_dir()


def test_status_counts_known_artifacts(tmp_path: Path) -> None:
    selected = tmp_path / "data/01_selected/targets/normalized/posts.jsonl"
    selected.parent.mkdir(parents=True)
    selected.write_text('{"x": 1}\n{"x": 2}\n', encoding="utf-8")

    media_post = tmp_path / "data/02_media/tiktok/account/post-1"
    media_post.mkdir(parents=True)
    (media_post / "meta.json").write_text("{}", encoding="utf-8")

    rows = {row["label"]: row for row in status_rows(tmp_path)}
    assert rows["selected normalized posts"]["count"] == 2
    assert rows["local media posts"]["count"] == 1
    assert rows["creative master"]["present"] is False


def test_doctor_checks_environment_without_crashing(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_TOKEN", "test-apify")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    checks = {name: (ok, detail, required) for name, ok, detail, required in doctor_checks()}
    assert checks["env:APIFY_TOKEN"] == (True, "set", False)
    assert checks["env:GEMINI_API_KEY"] == (True, "set", False)
