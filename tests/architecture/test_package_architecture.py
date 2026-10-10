from __future__ import annotations

import ast
import os
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

from creative_research.cli.registry import COMMANDS

PACKAGE = Path(__file__).resolve().parents[2] / "src/creative_research"


def _module_graph():
    paths = {
        "creative_research." + ".".join(path.relative_to(PACKAGE).with_suffix("").parts): path
        for path in PACKAGE.rglob("*.py")
    }
    paths = {name.removesuffix(".__init__"): path for name, path in paths.items()}
    graph = {name: set() for name in paths}
    for name, path in paths.items():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = name if path.name == "__init__.py" else name.rpartition(".")[0]
                imported = resolve_name("." * node.level + (node.module or ""), package)
                imports = [imported] + [imported + "." + alias.name for alias in node.names]
            graph[name].update(module for module in imports if module in paths)
    return graph


def test_package_has_no_local_import_cycles_and_analysis_is_provider_independent():
    graph = _module_graph()
    visited = set()

    def visit(module, active):
        assert module not in active, f"Import cycle: {' -> '.join((*active, module))}"
        if module in visited:
            return
        for dependency in graph[module]:
            visit(dependency, (*active, module))
        visited.add(module)

    for module in graph:
        visit(module, ())
        if (
            not module.startswith("creative_research.cli")
            and module != "creative_research.__main__"
        ):
            assert not any(
                dependency.startswith("creative_research.cli") for dependency in graph[module]
            ), f"Business/infrastructure code must not depend on CLI: {module}"
    for path in (PACKAGE / "analysis").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            assert not any(
                imported.startswith(
                    ("google", "apify_client", "httpx", "urllib.request", "argparse")
                )
                for imported in imports
            ), path


def test_package_root_contains_only_bootstrap_and_shared_primitives():
    assert {path.name for path in PACKAGE.glob("*.py")} == {
        "__init__.py",
        "__main__.py",
        "constants.py",
        "errors.py",
        "identity.py",
    }


def test_argument_parsing_and_provider_dependencies_stay_in_their_adapters():
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        for node in ast.walk(ast.parse(path.read_text())):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            if any(name.startswith("argparse") for name in imports):
                assert relative.parts[0] == "cli", path
            if any(name.startswith(("google", "apify_client")) for name in imports):
                assert (
                    relative.parts[0] in {"capture", "vision"}
                    or relative.as_posix() == "infrastructure/gemini.py"
                ), path


def test_command_catalog_cannot_be_mutated():
    with pytest.raises(TypeError):
        COMMANDS["unexpected-command"] = "creative_research.cli.commands.demo"


def test_importing_entire_package_does_not_load_config_make_requests_or_write_files(tmp_path):
    (tmp_path / ".env").write_text("CREATIVE_RESEARCH_IMPORT_SENTINEL=must-not-load\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("CREATIVE_RESEARCH_") and key not in {"GEMINI_API_KEY", "APIFY_TOKEN"}
    }
    env["PYTHONPATH"] = str(PACKAGE.parent)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = """
import importlib, os, pkgutil
from unittest.mock import patch
import apify_client, httpx, pandas
from google import genai
import creative_research
def forbidden(*args, **kwargs):
    raise AssertionError("Import-time external effect")
with patch.object(genai, "Client", forbidden), patch.object(apify_client, "ApifyClient", forbidden), \\
     patch.object(httpx.Client, "request", forbidden), patch.object(pandas, "read_csv", forbidden), \\
     patch.object(pandas, "read_parquet", forbidden):
    for module in pkgutil.walk_packages(creative_research.__path__, creative_research.__name__ + "."):
        importlib.import_module(module.name)
assert "CREATIVE_RESEARCH_IMPORT_SENTINEL" not in os.environ
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == [tmp_path / ".env"]
