"""Explicit, typed Gemini configuration and connection lifetime management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from math import ceil, isfinite

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel


def is_retryable_api_error(error: Exception) -> bool:
    """Retry transient transport/status failures, never arbitrary programming errors."""
    status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if value is not None:
            try:
                status = int(value)
            except (TypeError, ValueError):
                continue
            break
    if status is not None:
        return status in {408, 409, 429} or 500 <= status < 600
    return isinstance(error, (TimeoutError, ConnectionError, httpx.TransportError))


@contextmanager
def gemini_client(api_key: str, *, timeout_seconds: float) -> Iterator[genai.Client]:
    """Release provider connections on success, failure and interruption."""
    if not isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Gemini timeout must be a finite positive number of seconds")
    with genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=max(1, ceil(timeout_seconds * 1000))),
    ) as client:
        yield client


def build_generation_config(
    schema: type[BaseModel],
    *,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    thinking_level: types.ThinkingLevel | None = None,
) -> types.GenerateContentConfig:
    """Use supported SDK options; invalid configuration must not be silently retried."""
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking_config=(
            types.ThinkingConfig(thinking_level=thinking_level)
            if thinking_level is not None
            else None
        ),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
