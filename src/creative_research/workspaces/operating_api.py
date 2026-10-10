"""Local loopback-only team operations. One live write API, one durable store."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from creative_research.infrastructure.http import (
    loopback_host,
    read_json_request,
    respond,
    same_origin_json_request,
)
from creative_research.operating.state import OperatingError, OperatingStore


def handle_operating_get(
    handler: BaseHTTPRequestHandler,
    service: OperatingStore | None,
) -> bool:
    path = urlparse(handler.path).path
    if path not in {"/api/operating", "/api/operating/export"}:
        return False
    if not loopback_host(handler):
        respond(handler, 403, {"error": "loopback_host_required"})
        return True
    if service is None:
        respond(handler, 503, {"error": "operating_state_unavailable"})
        return True
    try:
        if path == "/api/operating/export":
            payload = service.export_zip()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/zip")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header(
                "Content-Disposition",
                'attachment; filename="operator-team-handoff.zip"',
            )
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
        else:
            respond(handler, 200, service.view())
    except OperatingError as exc:
        respond(handler, 409, {"error": str(exc)})
    return True


def handle_operating_post(
    handler: BaseHTTPRequestHandler,
    service: OperatingStore | None,
    *,
    read_only: bool,
) -> bool:
    if urlparse(handler.path).path != "/api/operating":
        return False
    if read_only or service is None:
        respond(handler, 403, {"error": "operating_read_only"})
        return True
    if not loopback_host(handler) or not same_origin_json_request(handler):
        respond(handler, 403, {"error": "same_origin_loopback_json_required"})
        return True
    payload = read_json_request(handler, max_bytes=20000)
    if payload is None:
        return True

    try:
        result = service.mutate(payload)
    except OperatingError as exc:
        respond(handler, 409, {"error": str(exc)})
        return True
    respond(handler, 200, {"ok": True, "operating": result})
    return True
