"""Small TTY-aware presentation layer; no decoration leaks into redirected output."""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from collections.abc import Iterable
from typing import TextIO

from creative_research.infrastructure.logging import redact


class Console:
    def __init__(self, stream: TextIO | None = None, *, color: str = "auto") -> None:
        self.stream = stream if stream is not None else sys.stdout
        self.color = color == "always" or (
            color == "auto"
            and self.stream.isatty()
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )

    def write(self, value: str = "", *, style: str = "") -> None:
        value = redact(value)
        if self.color and style:
            value = f"\033[{style}m{value}\033[0m"
        print(value, file=self.stream)

    def heading(self, title: str) -> None:
        self.write(title, style="1;36")

    def rows(self, values: Iterable[tuple[str, str]]) -> None:
        columns = shutil.get_terminal_size(fallback=(100, 24)).columns
        for name, description in values:
            if columns < 72:
                self.write("  " + name)
                for line in textwrap.wrap(description, width=max(20, columns - 4)):
                    self.write("    " + line)
                continue
            prefix = f"  {name:<28} "
            wrapped = textwrap.wrap(description, width=min(66, columns - len(prefix))) or [""]
            self.write(prefix + wrapped[0])
            for line in wrapped[1:]:
                self.write(" " * len(prefix) + line)

    def error(self, message: str, *, hint: str = "") -> None:
        self.write(f"Error: {message}", style="1;31")
        if hint:
            self.write(f"Hint: {hint}", style="33")
