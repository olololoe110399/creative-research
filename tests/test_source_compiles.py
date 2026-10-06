from __future__ import annotations

import py_compile
from pathlib import Path


def test_all_source_files_compile() -> None:
    root = Path(__file__).resolve().parents[1] / "src"
    for path in root.rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
