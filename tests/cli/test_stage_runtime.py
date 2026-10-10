from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from creative_research.cli import runtime as stage_runtime
from creative_research.cli.app import dispatch_stage
from creative_research.infrastructure.paths import project_root


@pytest.mark.parametrize("previous_root", [None, "/previous/project"])
@pytest.mark.parametrize("exit_code", [None, 2])
def test_stage_invocation_restores_arguments_and_project_root(
    tmp_path,
    monkeypatch,
    previous_root,
    exit_code,
) -> None:
    key = "CREATIVE_RESEARCH_PROJECT_ROOT"
    if previous_root is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, previous_root)
    old_argv = sys.argv
    seen = []

    def main():
        seen.append((sys.argv[:], project_root()))
        if exit_code is not None:
            raise SystemExit(exit_code)

    monkeypatch.setattr(stage_runtime, "import_module", lambda _: SimpleNamespace(main=main))
    if exit_code is None:
        stage_runtime.run_stage("example", ["--flag", "value"], root=tmp_path)
    else:
        with pytest.raises(SystemExit) as error:
            stage_runtime.run_stage("example", ["--flag", "value"], root=tmp_path)
        assert error.value.code == exit_code
    assert seen == [(["example", "--flag", "value"], tmp_path)]
    assert sys.argv is old_argv
    assert os.environ.get(key) == previous_root


def test_cli_dispatch_uses_shared_runtime_and_preserves_stage_exit(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        stage_runtime,
        "import_module",
        lambda module: SimpleNamespace(main=lambda: calls.append((module, sys.argv[:]))),
    )
    assert dispatch_stage("lab", ["--help"]) == 0
    assert calls == [("creative_research.cli.commands.lab", ["creative-research lab", "--help"])]
