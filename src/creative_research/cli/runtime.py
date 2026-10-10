"""Invoke CLI stages without re-executing their module-level definitions."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path

from creative_research.infrastructure.config import project_context


def run_stage(
    module: str,
    args: Sequence[str],
    *,
    root: Path | None = None,
    prog: str | None = None,
) -> None:
    old_argv = sys.argv
    try:
        sys.argv = [prog or module, *args]
        with project_context(root):
            import_module(module).main()
    finally:
        sys.argv = old_argv
