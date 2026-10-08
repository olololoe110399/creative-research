"""Local loopback-only team operations. One live write API, one durable store."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from creative_research.ai_endpoints import loopback_host, respond, same_origin_json_request
from creative_research.operating_state import OperatingError, OperatingStore


def handle_operating_get(
    handler: BaseHTTPRequestHandler,
    service: OperatingStore | None,
) -> bool:
    path=urlparse(handler.path).path
    if path not in {"/api/operating","/api/operating/export"}:
        return False
    if not loopback_host(handler):
        respond(handler,403,{"error":"loopback_host_required"})
        return True
    if service is None:
        respond(handler,503,{"error":"operating_state_unavailable"})
        return True
    try:
        if path == "/api/operating/export":
            payload=service.export_zip()
            handler.send_response(200)
            handler.send_header("Content-Type","application/zip")
            handler.send_header("Cache-Control","no-store")
            handler.send_header("X-Content-Type-Options","nosniff")
            handler.send_header(
                "Content-Disposition",
                'attachment; filename="operator-team-handoff.zip"',
            )
            handler.send_header("Content-Length",str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
        else:
            respond(handler,200,service.view())
    except OperatingError as exc:
        respond(handler,409,{"error":str(exc)})
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
        respond(handler,403,{"error":"operating_read_only"})
        return True
    if not loopback_host(handler) or not same_origin_json_request(handler):
        respond(handler,403,{"error":"same_origin_loopback_json_required"})
        return True
    try:
        size=int(handler.headers.get("Content-Length") or 0)
    except (TypeError,ValueError):
        size=0
    if size < 2 or size > 20000:
        respond(handler,400,{"error":"invalid_request_size"})
        return True
    try:
        payload=json.loads(handler.rfile.read(size).decode("utf-8"))
    except (ValueError,UnicodeDecodeError):
        respond(handler,400,{"error":"invalid_json"})
        return True
    if not isinstance(payload,dict):
        respond(handler,400,{"error":"invalid_payload"})
        return True
    try:
        result=service.mutate(payload)
    except OperatingError as exc:
        respond(handler,409,{"error":str(exc)})
        return True
    respond(handler,200,{"ok":True,"operating":result})
    return True
