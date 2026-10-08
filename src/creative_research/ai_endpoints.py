"""Safe, opt-in AI routes for the localhost Operator Lab.

The endpoint never accepts arbitrary prompts or filesystem paths, and never
writes trust decisions. The research service uses only materialized Lab JSON.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from creative_research.ai_research import AIResearchService, ResearchValidationError


def same_origin_json_request(handler: BaseHTTPRequestHandler) -> bool:
    """Browser cross-site requests must not spend tokens or write reviews."""
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return False
    if handler.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        return False
    origin = handler.headers.get("Origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc.lower() != handler.headers.get("Host", "").lower():
            return False
    return True


def respond(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(raw)


def handle_ai_get(
    handler: BaseHTTPRequestHandler,
    service: AIResearchService | None,
    path: str,
) -> bool:
    if path == "/api/ai/status":
        respond(
            handler, 200,
            service.status() if service is not None
            else {"enabled": False, "configured": False, "reason": "ai_disabled"},
        )
        return True
    if path.startswith("/api/ai/report/"):
        if service is None or not service.enabled:
            respond(handler, 403, {"error": "ai_research_disabled"})
            return True
        try:
            report_id = path.removeprefix("/api/ai/report/")
            respond(handler, 200, service.load(report_id))
        except ResearchValidationError as exc:
            respond(handler, 404, {"error": str(exc)})
        return True
    return False


def handle_ai_post(
    handler: BaseHTTPRequestHandler,
    service: AIResearchService | None,
    *,
    read_only: bool,
) -> bool:
    path = urlparse(handler.path).path
    if path not in {"/api/ai/plan", "/api/ai/run"}:
        return False
    if service is None:
        respond(handler, 403, {"error": "ai_research_disabled"})
        return True
    if not same_origin_json_request(handler):
        respond(handler, 403, {"error": "same_origin_json_required"})
        return True
    if path.endswith("/run") and (read_only or not service.enabled):
        respond(handler, 403, {"error": "ai_disabled_or_read_only"})
        return True
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError:
        length = 0
    if not (1 <= length <= 2048):
        respond(handler, 400, {"error": "invalid_request_size"})
        return True
    try:
        body = json.loads(handler.rfile.read(length).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        respond(handler, 400, {"error": "invalid_json"})
        return True
    if not isinstance(body, dict):
        respond(handler, 400, {"error": "invalid_payload"})
        return True
    mode, kind, target = (
        body.get("mode"), body.get("source_type"), body.get("source_id")
    )
    if not all(isinstance(item, str) and 0 < len(item) <= 256
               for item in (mode, kind, target)):
        respond(handler, 400, {"error": "invalid_research_request"})
        return True
    try:
        if path.endswith("/plan"):
            _packet, metadata = service.plan(mode, kind, target)
            respond(handler, 200, {"ok": True, "plan": metadata})
        else:
            report = service.run(mode, kind, target)
            respond(handler, 200, {"ok": True, "report": report})
    except ResearchValidationError as exc:
        name = str(exc)
        status = 429 if name == "ai_call_limit_reached" else 400
        respond(handler, status, {"error": name})
    except Exception:
        # Do not serialize provider exception text (which may contain credentials,
        # excerpts of public posts, or API response metadata).
        respond(handler, 502, {"error": "ai_provider_or_validation_failed"})
    return True
