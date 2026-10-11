from __future__ import annotations

import json

import pytest

from creative_research import __version__
from creative_research.cli import app as cli
from creative_research.cli.console import Console
from creative_research.cli.registry import COMMAND_SPECS


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
                "download-media",
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
    assert "download-media --input" in out
    assert "\x1b[" not in out
    assert cli.execute(["--version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_unknown_command_has_actionable_suggestion(capsys) -> None:
    assert cli.execute(["download-medai"]) == 2
    assert "Did you mean 'download-media'" in capsys.readouterr().err


def test_root_and_quiet_keep_machine_output_visible(tmp_path, capsys) -> None:
    assert cli.execute(["init", "--root", str(tmp_path), "--quiet", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project"] == str(tmp_path)
    assert (tmp_path / "data/raw").is_dir()
    assert cli.execute(["status", "--root", str(tmp_path), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


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
