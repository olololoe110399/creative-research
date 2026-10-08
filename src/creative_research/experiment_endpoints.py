"""First-party experiment selection API; cannot approve operator claims."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from creative_research.http_local import (
    loopback_host, respond, same_origin_json_request,
)
from creative_research.experiment_plan import ExperimentPlanError, ExperimentPlanStore


def handle_experiment_get(
    handler: BaseHTTPRequestHandler,
    service: ExperimentPlanStore | None,
) -> bool:
    if urlparse(handler.path).path != "/api/experiments":
        return False
    if not loopback_host(handler):
        respond(handler, 403, {"error": "loopback_host_required"})
        return True
    if service is None:
        respond(handler, 503, {"error": "experiment_plan_unavailable"})
        return True
    try:
        respond(handler, 200, service.view())
    except ExperimentPlanError as exc:
        respond(handler, 409, {"error": str(exc)})
    return True


def handle_experiment_post(
    handler: BaseHTTPRequestHandler,
    service: ExperimentPlanStore | None,
    *, read_only: bool,
) -> bool:
    if urlparse(handler.path).path != "/api/experiments":
        return False
    if read_only or service is None:
        respond(handler, 403, {"error": "experiment_plan_read_only"})
        return True
    if not loopback_host(handler) or not same_origin_json_request(handler):
        respond(handler, 403, {"error": "same_origin_loopback_json_required"})
        return True
    try:
        size = int(handler.headers.get("Content-Length") or 0)
    except (ValueError, TypeError):
        size = 0
    if size < 2 or size > 8192:
        respond(handler, 400, {"error": "invalid_request_size"})
        return True
    try:
        payload = json.loads(handler.rfile.read(size).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        respond(handler, 400, {"error": "invalid_json"})
        return True
    if not isinstance(payload, dict):
        respond(handler, 400, {"error": "invalid_payload"})
        return True
    fields = ("key", "action", "state", "notes", "metric_observed")
    if any(k in payload and not isinstance(payload[k], str) for k in fields):
        respond(handler, 400, {"error": "invalid_experiment_fields"})
        return True
    try:
        result = service.mutate(
            key=payload.get("key", ""),
            action=payload.get("action", ""),
            state=payload.get("state", "planned"),
            notes=payload.get("notes", ""),
            metric_observed=payload.get("metric_observed", ""),
        )
    except ExperimentPlanError as exc:
        respond(handler, 409, {"error": str(exc)})
        return True
    respond(handler, 200, {"ok": True, "plan": result})
    return True
