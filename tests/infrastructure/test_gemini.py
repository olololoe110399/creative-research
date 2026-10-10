from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import types
from pydantic import BaseModel

from creative_research.infrastructure import gemini


class ResponseContract(BaseModel):
    accepted: bool


@pytest.mark.parametrize("failure", [None, OSError("disk error"), KeyboardInterrupt()])
def test_client_context_closes_on_success_failure_and_interrupt(monkeypatch, failure):
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)

    def operation():
        with gemini.gemini_client("synthetic-key", timeout_seconds=2.5) as client:
            assert client is factory.return_value.__enter__.return_value
            if failure is not None:
                raise failure

    if failure is None:
        operation()
    else:
        with pytest.raises(type(failure)):
            operation()
    assert factory.call_args.kwargs["http_options"].timeout == 2500
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_client_rejects_invalid_timeout_without_opening_connection(monkeypatch, timeout):
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    with (
        pytest.raises(ValueError, match="finite positive"),
        gemini.gemini_client("synthetic", timeout_seconds=timeout),
    ):
        pytest.fail("Invalid timeout entered client context")
    factory.assert_not_called()


def test_sub_millisecond_timeout_is_not_rounded_to_disabled_timeout(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    with gemini.gemini_client("synthetic", timeout_seconds=0.0001):
        assert factory.call_args.kwargs["http_options"].timeout == 1


def test_generation_configuration_uses_supported_typed_sdk_contract():
    config = gemini.build_generation_config(
        ResponseContract,
        temperature=0.1,
        max_output_tokens=256,
        thinking_level=types.ThinkingLevel.MINIMAL,
    )
    assert config.response_schema is ResponseContract
    assert config.response_mime_type == "application/json"
    assert config.automatic_function_calling.disable is True
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert config.max_output_tokens == 256


def test_invalid_sdk_configuration_is_not_silently_replaced(monkeypatch):
    factory = MagicMock(side_effect=TypeError("unsupported option"))
    monkeypatch.setattr(gemini.types, "GenerateContentConfig", factory)
    with pytest.raises(TypeError, match="unsupported option"):
        gemini.build_generation_config(ResponseContract)
    factory.assert_called_once()


@pytest.mark.parametrize(
    ("status", "retry"),
    [
        (400, False),
        (401, False),
        (404, False),
        (408, True),
        (409, True),
        (429, True),
        (500, True),
        (503, True),
        (600, False),
    ],
)
def test_http_status_retry_policy(status, retry):
    request = httpx.Request("GET", "https://example.test")
    error = httpx.HTTPStatusError("synthetic", request=request, response=httpx.Response(status))
    assert gemini.is_retryable_api_error(error) is retry


@pytest.mark.parametrize(
    ("error", "retry"),
    [
        (TimeoutError(), True),
        (ConnectionError(), True),
        (httpx.ReadTimeout("timeout"), True),
        (KeyError("404"), False),
        (TypeError("429"), False),
        (RuntimeError("500"), False),
    ],
)
def test_retry_does_not_guess_status_from_error_text(error, retry):
    assert gemini.is_retryable_api_error(error) is retry


def test_sdk_error_status_takes_precedence_over_transport_class():
    error = ConnectionError("synthetic")
    error.code = "403"
    assert gemini.is_retryable_api_error(error) is False
    error.code = "503"
    assert gemini.is_retryable_api_error(error) is True
