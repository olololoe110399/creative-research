"""Find local implementation dependencies without importing provider/CLI modules."""

from __future__ import annotations

import ast
from functools import cache
from importlib.util import resolve_name
from pathlib import Path


@cache
def implementation_sources(module: str) -> tuple[Path, ...]:
    package = Path(__file__).resolve().parents[1]
    visited: set[str] = set()
    sources: set[Path] = set()

    def visit(name: str) -> None:
        if (
            not (name == "creative_research" or name.startswith("creative_research."))
            or name in visited
        ):
            return
        visited.add(name)
        parts = name.split(".")[1:]
        path = package.joinpath(*parts).with_suffix(".py") if parts else package / "__init__.py"
        if not path.is_file():
            path = package.joinpath(*parts, "__init__.py")
        if not path.is_file():
            return
        sources.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    visit(alias.name)
            elif isinstance(node, ast.ImportFrom):
                context = name if path.name == "__init__.py" else name.rpartition(".")[0]
                imported = resolve_name("." * node.level + (node.module or ""), context)
                visit(imported)
                for alias in node.names:
                    visit(imported + "." + alias.name)

    visit(module)
    return tuple(sorted(sources))
