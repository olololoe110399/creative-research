from __future__ import annotations

from pathlib import Path

from creative_research.cli.registry import COMMANDS
from creative_research.cli.workspace import cmd_init
from creative_research.constants import WORKSPACE_DIRS
from creative_research.infrastructure.workspace import doctor_checks, status_rows


def test_canonical_commands_exist() -> None:
    assert set(COMMANDS) == {"run", "scrape", "download-media", "export-dataset"}


def test_init_creates_canonical_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    assert cmd_init([]) == 0
    for rel in WORKSPACE_DIRS:
        assert (tmp_path / rel).is_dir()


def test_status_counts_known_artifacts(tmp_path: Path) -> None:
    record = tmp_path / "data/raw/run-001/posts/creator.jsonl"
    record.parent.mkdir(parents=True)
    record.write_text("{}\n")
    rows = {row["label"]: row for row in status_rows(tmp_path)}
    assert rows["crawl records"]["count"] == 1
    assert rows["media files"]["present"] is False


def test_doctor_checks_environment_without_crashing(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_TOKEN", "test-apify")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    checks = {name: (ok, detail, required) for name, ok, detail, required in doctor_checks()}
    assert checks["env:APIFY_TOKEN"] == (True, "set", False)
    assert "env:GEMINI_API_KEY" not in checks
