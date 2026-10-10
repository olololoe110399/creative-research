from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from skills_ref import read_properties, validate

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/creative-research"


def test_canonical_skill_is_spec_valid_and_all_progressive_links_resolve():
    assert validate(SKILL) == []
    props = read_properties(SKILL)
    assert props.name == "creative-research"
    assert props.compatibility
    for path in SKILL.rglob("*.md"):
        for value in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
            assert (path.parent / value).resolve().is_file(), (path, value)


def test_installation_copies_single_source_for_both_hosts_and_runs_outside_checkout(
    skill_modules, tmp_path
):
    _, _, installer = skill_modules
    installed = installer.install(SKILL, tmp_path, ["claude", "codex"])
    for target in installed:
        assert validate(target) == []
        assert (target / "SKILL.md").read_bytes() == (SKILL / "SKILL.md").read_bytes()
        assert not list(target.rglob("*.pyc"))
        result = subprocess.run(
            [sys.executable, str(target / "scripts/doctor.py")],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            timeout=40,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["providers_called"] is False
        result = subprocess.run(
            [sys.executable, str(target / "scripts/run_cli.py"), "--root", str(tmp_path), "status"],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            timeout=40,
        )
        assert result.returncode == 0, result.stderr


def test_installer_preflights_all_targets_and_preserves_existing_work(skill_modules, tmp_path):
    _, _, installer = skill_modules
    existing = tmp_path / ".agents/skills/creative-research"
    existing.mkdir(parents=True)
    sentinel = existing / "SKILL.md"
    sentinel.write_text("user work")
    with pytest.raises(ValueError, match="Already installed"):
        installer.install(SKILL, tmp_path, ["claude", "codex"])
    assert sentinel.read_text() == "user work"
    assert not (tmp_path / ".claude").exists()


def test_installer_rejects_symlinked_discovery_directory(skill_modules, tmp_path):
    _, _, installer = skill_modules
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked"):
        installer.install(SKILL, tmp_path, ["codex"])
    assert list(outside.iterdir()) == []


def test_source_snapshot_includes_portable_skill_without_private_outputs(skill_modules):
    import verify_distribution

    files = verify_distribution.source_files()
    assert "skills/creative-research/SKILL.md" in files
    assert "skills/creative-research/scripts/run_cli.py" in files
    assert "scripts/install_agent_skill.py" in files
    assert not any(name.startswith((".agents/", ".claude/", "agent-reports/")) for name in files)
