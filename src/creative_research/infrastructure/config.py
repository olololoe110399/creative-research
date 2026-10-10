"""Explicit, validated process configuration; importing this module has no side effects."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT_VARIABLE = "CREATIVE_RESEARCH_PROJECT_ROOT"
PREFIX = "CREATIVE_RESEARCH_"


def _positive_number(env: Mapping[str, str], name: str, default: float) -> float:
    import math

    raw = env.get(PREFIX + name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{PREFIX}{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{PREFIX}{name} must be a finite positive number")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    project_root: Path
    log_level: str = "INFO"
    log_format: str = "text"
    request_timeout: float = 30.0
    subprocess_timeout: float = 900.0
    server_request_timeout: float = 15.0
    ai_timeout: float = 90.0

    @classmethod
    def from_environ(cls, env: Mapping[str, str] | None = None) -> RuntimeSettings:
        values = os.environ if env is None else env
        root = Path(values.get(ROOT_VARIABLE) or Path.cwd()).expanduser().resolve()
        level = values.get(PREFIX + "LOG_LEVEL", "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"{PREFIX}LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
        log_format = values.get(PREFIX + "LOG_FORMAT", "text").lower()
        if log_format not in {"text", "json"}:
            raise ValueError(f"{PREFIX}LOG_FORMAT must be text or json")
        return cls(
            project_root=root,
            log_level=level,
            log_format=log_format,
            request_timeout=_positive_number(values, "REQUEST_TIMEOUT", 30.0),
            subprocess_timeout=_positive_number(values, "SUBPROCESS_TIMEOUT", 900.0),
            server_request_timeout=_positive_number(values, "SERVER_REQUEST_TIMEOUT", 15.0),
            ai_timeout=_positive_number(values, "AI_TIMEOUT", 90.0),
        )


def load_env_file(path: Path, env: MutableMapping[str, str] | None = None) -> None:
    """Load an explicitly selected UTF-8 KEY=value file without executing/interpolating it.

    Existing process variables win. Parse everything before changing the environment.
    Never include a value in a configuration error.
    """
    parsed: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid environment assignment at {path}:{number}")
        try:
            tokens = shlex.split(raw, comments=True, posix=True)
        except ValueError as exc:
            raise ValueError(f"Invalid environment quoting at {path}:{number}") from exc
        if len(tokens) > 1:
            raise ValueError(f"Quote whitespace in environment values at {path}:{number}")
        parsed[key] = tokens[0] if tokens else ""
    target = os.environ if env is None else env
    for key, value in parsed.items():
        target.setdefault(key, value)


@contextmanager
def project_context(root: Path | None) -> Iterator[None]:
    """Scope a project override without changing the working directory."""
    previous = os.environ.get(ROOT_VARIABLE)
    try:
        if root is not None:
            os.environ[ROOT_VARIABLE] = str(root.expanduser().resolve())
        yield
    finally:
        if root is not None:
            if previous is None:
                os.environ.pop(ROOT_VARIABLE, None)
            else:
                os.environ[ROOT_VARIABLE] = previous
