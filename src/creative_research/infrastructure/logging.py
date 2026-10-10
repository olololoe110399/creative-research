"""Application-only structured logging with credential redaction on stderr."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TextIO

_CREDENTIAL = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|bearer\s+|[?&](?:token|key|api_key|access_token)=)([^\s&\"']+)"
)


def redact(value: str) -> str:
    result = _CREDENTIAL.sub(r"\1[REDACTED]", value)
    for name, secret in os.environ.items():
        if any(part in name.upper() for part in ("TOKEN", "KEY", "PASSWORD", "SECRET")):
            if len(secret) >= 4:
                result = result.replace(secret, "[REDACTED]")
    return result


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _safe_fields(value)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    return redact(str(value)) if not isinstance(value, (int, float, bool, type(None))) else value


def _safe_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in fields.items():
        if any(
            part in key.lower()
            for part in ("token", "api_key", "password", "secret", "authorization")
        ):
            result[key] = "[REDACTED]"
        else:
            result[key] = _safe_value(value)
    return result


class RedactingFormatter(logging.Formatter):
    def __init__(self, *, structured: bool) -> None:
        super().__init__("%(levelname)s %(message)s")
        self.structured = structured

    def format(self, record: logging.LogRecord) -> str:
        context = getattr(record, "context", None)
        if not self.structured:
            rendered = super().format(record)
            if isinstance(context, Mapping):
                fields = _safe_fields(context)
                if record.getMessage() in {"stage_started", "stage_complete"}:
                    state = "running" if record.getMessage() == "stage_started" else "complete"
                    elapsed = f" ({fields['seconds']}s)" if "seconds" in fields else ""
                    rendered = f"{record.levelname} [{fields.get('step')}/{fields.get('total')}] {fields.get('stage')}: {state}{elapsed}"
                else:
                    rendered += " " + " ".join(f"{key}={value}" for key, value in fields.items())
            return redact(rendered)
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": redact(record.getMessage()),
        }
        if isinstance(context, Mapping):
            payload["context"] = _safe_fields(context)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


@contextmanager
def logging_context(*, level: str, log_format: str, stream: TextIO) -> Iterator[None]:
    logger = logging.getLogger("creative_research")
    previous = (logger.handlers[:], logger.level, logger.propagate)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter(structured=log_format == "json"))
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield
    finally:
        logger.handlers, logger.level, logger.propagate = previous
        handler.close()
