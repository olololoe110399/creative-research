from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def release_tools(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    return importlib.import_module("verify_distribution"), importlib.import_module(
        "generate_cli_docs"
    )


def test_source_allowlist_excludes_private_data_caches_and_history(release_tools):
    distribution, _ = release_tools
    files = distribution.source_files()
    assert "LICENSE" in files and ".env.example" in files and ".python-version" in files
    assert not any(name.startswith(("data/", ".git/", ".venv/")) for name in files)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in files)
    assert "zip.py" not in files and "CHANGELOG.md" not in files and "MIGRATION.md" not in files
    assert "src/creative_research/ai_research.py" not in files


def test_secret_audit_reports_location_without_exposing_match(release_tools):
    distribution, _ = release_tools
    secret = "apify_" + "api_" + "a" * 30
    with pytest.raises(ValueError) as error:
        distribution.audit_text("example.py", ("safe\n" + secret).encode())
    assert "example.py:2: Apify token" in str(error.value)
    assert secret not in str(error.value)


def test_public_allowlist_rejects_accidental_private_configuration(release_tools, tmp_path):
    distribution, _ = release_tools
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.0.0"\nlicense = "MIT"\n'
        '[tool.hatch.build.targets.sdist]\ninclude = ["/config/private.toml"]\n'
    )
    config = tmp_path / "config"
    config.mkdir()
    (config / "private.toml").write_text("private = true")
    with pytest.raises(ValueError, match="Unexpected public release input"):
        distribution.source_files(tmp_path)


def test_distribution_metadata_requires_consistent_version_and_license(release_tools):
    distribution, _ = release_tools
    valid = (
        b"Name: creative-research\nVersion: 1.0.0\nLicense-Expression: MIT\nLicense-File: LICENSE\n"
    )
    distribution.check_metadata(valid)
    with pytest.raises(ValueError, match="differs"):
        distribution.check_metadata(valid.replace(b"1.0.0", b"99.0.0"))
    with pytest.raises(ValueError, match="missing the MIT license"):
        distribution.check_metadata(valid.replace(b"License-Expression: MIT\n", b""))


def test_documentation_checks_reject_bad_links_commands_and_options(release_tools, tmp_path):
    _, docs = release_tools
    path = tmp_path / "README.md"
    path.write_text("[broken](missing.md)")
    with pytest.raises(ValueError, match="Broken documentation link"):
        docs.validate_docs(tmp_path)
    path.write_text("```sh\ncreative-research invented-command\n```\n")
    with pytest.raises(ValueError, match="Unknown documented command"):
        docs.validate_docs(tmp_path)
    path.write_text("```sh\ncreative-research demo --invented-option value\n```\n")
    with pytest.raises(ValueError, match="Invalid CLI example"):
        docs.validate_docs(tmp_path)


def test_documentation_examples_are_parsed_without_execution(release_tools, tmp_path):
    _, docs = release_tools
    path = tmp_path / "README.md"
    path.write_text(
        "```sh\ncreative-research demo --out should-not-exist\ncreative-research scrape fake.txt\n```\n"
    )
    assert docs.validate_docs(tmp_path) == (0, 2)
    assert list(tmp_path.iterdir()) == [path]
