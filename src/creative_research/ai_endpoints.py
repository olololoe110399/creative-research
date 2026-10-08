"""Safe, opt-in AI routes for the localhost Operator Lab.

The endpoint never accepts arbitrary prompts or filesystem paths, and never
writes trust decisions. The research service uses only materialized Lab JSON.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from creative_research.ai_research import AIResearchService, ResearchValidationError
from creative_research.http_local import loopback_host, same_origin_json_request, respond


def handle_ai_get(
    handler: BaseHTTPRequestHandler,
    service: AIResearchService | None,
    path: str,
) -> bool:
    parsed = urlparse(path)
    pathname = parsed.path
    if (pathname in {"/api/ai/status", "/api/ai/history"}
            or pathname.startswith("/api/ai/report/")) and not loopback_host(handler):
        respond(handler, 403, {"error": "loopback_host_required"})
        return True
    if pathname == "/api/ai/status":
        respond(
            handler, 200,
            service.status() if service is not None
            else {"enabled": False, "configured": False, "reason": "ai_disabled"},
        )
        return True
    if pathname == "/api/ai/history":
        if service is None:
            respond(handler, 403, {"error": "ai_research_disabled"})
            return True
        params = parse_qs(parsed.query, keep_blank_values=False)
        kind = params.get("source_type", [""])[0]
        source_id = params.get("source_id", [""])[0]
        if not all(isinstance(v, str) and 0 < len(v) <= 256
                   for v in (kind, source_id)):
            respond(handler, 400, {"error": "invalid_research_source"})
            return True
        try:
            respond(handler, 200, {"reports": service.history(kind, source_id)})
        except ResearchValidationError as exc:
            respond(handler, 404, {"error": str(exc)})
        return True
    if pathname.startswith("/api/ai/report/"):
        if service is None:
            respond(handler, 403, {"error": "ai_research_disabled"})
            return True
        try:
            report_id = pathname.removeprefix("/api/ai/report/")
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
    if not loopback_host(handler):
        respond(handler, 403, {"error": "loopback_host_required"})
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
