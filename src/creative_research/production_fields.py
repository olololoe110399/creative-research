"""Shared, deterministic production evidence field normalizers."""
from __future__ import annotations
import json
import re
import statistics
from typing import Any

def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    return " ".join(re.findall(r"\w+", _text(value).casefold(), flags=re.UNICODE))


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _clean_copy(value: Any, limit: int = 250) -> str:
    return _text(value).replace("\r", " ").replace("\n", " ")[:limit]


def _read_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else None
    except (ValueError, TypeError):
        return None


def _pct(post: dict[str, Any]) -> float | None:
    perf = post.get("performance") or {}
    return _num(perf.get("views_percentile_account") or post.get("account_views_pct"))


