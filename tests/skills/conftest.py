from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/creative-research"


@pytest.fixture
def skill_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SKILL / "scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return (
        importlib.import_module("run_cli"),
        importlib.import_module("validate_report"),
        importlib.import_module("install_agent_skill"),
    )
