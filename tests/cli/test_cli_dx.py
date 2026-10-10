from __future__ import annotations

import json
from pathlib import Path

import pytest

from creative_research import __version__
from creative_research.cli import app as cli
from creative_research.cli import workspace as workspace_commands
from creative_research.cli.console import Console
from creative_research.cli.registry import COMMAND_SPECS
from creative_research.infrastructure import workspace as workspace_service


@pytest.mark.parametrize(
    "color,no_color,expected",
    [("auto", False, True), ("auto", True, False), ("never", False, False), ("always", True, True)],
)
def test_console_tty_colors_and_no_color_preference(monkeypatch, color, no_color, expected) -> None:
    import io

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    stream = Terminal()
    monkeypatch.setenv("TERM", "xterm")
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    Console(stream, color=color).heading("Commands")
    assert ("\x1b[" in stream.getvalue()) is expected


def test_console_help_wraps_for_narrow_terminals(monkeypatch) -> None:
    import io
    import os

    from creative_research.cli import console

    monkeypatch.setattr(
        console.shutil, "get_terminal_size", lambda **kwargs: os.terminal_size((50, 24))
    )
    stream = io.StringIO()
    Console(stream).rows(
        [
            (
                "intelligence-build",
                "A sufficiently long description that should fit within this narrow terminal.",
            )
        ]
    )
    assert all(len(line) <= 50 for line in stream.getvalue().splitlines())


@pytest.mark.parametrize("command", [spec.name for spec in COMMAND_SPECS])
def test_every_command_has_help_without_writing_or_calling_providers(
    command, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    assert cli.execute([command, "--help"]) == 0
    assert "usage:" in capsys.readouterr().out.lower()
    assert list(tmp_path.iterdir()) == []


def test_help_is_generated_without_ansi_when_redirected(capsys) -> None:
    assert cli.execute(["--help"]) == 0
    out = capsys.readouterr().out
    assert "--env-file" in out
    assert "intelligence-build --dry-run --json" in out
    assert "\x1b[" not in out
    assert cli.execute(["--version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_unknown_command_has_actionable_suggestion(capsys) -> None:
    assert cli.execute(["inteligence-build"]) == 2
    assert "Did you mean 'intelligence-build'" in capsys.readouterr().err


def test_demo_builds_offline_in_empty_directory_and_refuses_overwrite(tmp_path, capsys) -> None:
    root = tmp_path / "demo"
    assert cli.execute(["demo", "--out", str(root), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "complete"
    assert len(report["stages"]) == 12
    assert json.loads((root / "SYNTHETIC_DEMO.json").read_text())["synthetic"] is True
    master = root / "data/05_master/creative_master.parquet"
    original = master.read_bytes()
    assert cli.execute(["demo", "--out", str(root)]) == 2
    assert master.read_bytes() == original


def test_root_and_quiet_keep_machine_output_visible(tmp_path, capsys) -> None:
    assert cli.execute(["init", "--root", str(tmp_path), "--quiet", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project"] == str(tmp_path)
    assert (tmp_path / "data/05_master").is_dir()
    assert cli.execute(["status", "--root", str(tmp_path), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_pipeline_json_is_one_document_and_dry_run_is_read_only(tmp_path, capsys) -> None:
    assert cli.execute(["--root", str(tmp_path), "intelligence-build", "--dry-run", "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "blocked"
    assert "Intelligence build plan" in captured.err
    assert list(tmp_path.iterdir()) == []


def test_error_boundary_redacts_and_maps_interrupts(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("APIFY_TOKEN", "secret-for-regression")

    def fail(*args):
        raise RuntimeError("request failed token: secret-for-regression")

    monkeypatch.setattr(cli, "dispatch_stage", fail)
    assert cli.execute(["--verbose", "scrape"]) == 1
    captured = capsys.readouterr()
    assert "secret-for-regression" not in captured.err
    assert "[REDACTED]" in captured.err

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "dispatch_stage", interrupt)
    assert cli.execute(["scrape"]) == 130

    def broken_pipe(*args):
        raise BrokenPipeError

    monkeypatch.setattr(cli, "dispatch_stage", broken_pipe)
    assert cli.execute(["scrape"]) == 0


def test_adopt_replace_preserves_recoverable_backup(tmp_path, monkeypatch) -> None:
    source, dest = tmp_path / "source", tmp_path / "destination"
    source.write_text("new")
    dest.write_text("old")
    workspace_service.adopt_artifact(str(source), dest, "copy", True)
    assert dest.read_text() == "new"
    backups = list(tmp_path.glob("destination.backup-*"))
    assert len(backups) == 1 and backups[0].read_text() == "old"


def test_adopt_copy_failure_leaves_old_destination_untouched(tmp_path, monkeypatch) -> None:
    source, dest = tmp_path / "source", tmp_path / "destination"
    source.write_text("new")
    dest.write_text("old")

    def fail(*args):
        raise OSError("copy failed")

    monkeypatch.setattr(workspace_service.shutil, "copy2", fail)
    with pytest.raises(OSError):
        workspace_service.adopt_artifact(str(source), dest, "copy", True)
    assert dest.read_text() == "old"
    assert not list(tmp_path.glob(".adopt-*"))


def test_adopt_publication_failure_restores_old_destination(tmp_path, monkeypatch) -> None:
    source, dest = tmp_path / "source", tmp_path / "destination"
    source.write_text("new")
    dest.write_text("old")
    original = Path.replace

    def fail_staged(path, target):
        if path.name == "artifact":
            raise OSError("publication failed")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail_staged)
    with pytest.raises(OSError):
        workspace_service.adopt_artifact(str(source), dest, "copy", True)
    assert dest.read_text() == "old"
    assert not list(tmp_path.glob("destination.backup-*"))


def test_adopt_preflights_all_inputs_and_rejects_unsafe_names(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    source = tmp_path / "existing"
    source.mkdir()
    with pytest.raises(ValueError, match="does not exist"):
        workspace_commands.cmd_adopt(
            ["--selected", str(source), "--media", str(tmp_path / "missing")]
        )
    assert not (tmp_path / "data").exists()
    with pytest.raises(ValueError, match="Invalid Apify"):
        workspace_commands.cmd_adopt(["--apify", "../escape=" + str(source)])
    with pytest.raises(ValueError, match="overlap"):
        workspace_service.adopt_artifact(str(source), source / "nested", "copy", True)
