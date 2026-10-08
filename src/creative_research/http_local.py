"""Lightweight reusable localhost security for all non-AI APIs."""
from __future__ import annotations
import json
import ipaddress
from typing import Any
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler

def loopback_host(handler: BaseHTTPRequestHandler) -> bool:
    """Block DNS-rebinding hosts even when Origin and Host happen to match."""
    name = urlparse("http://" + handler.headers.get("Host", "")).hostname
    if not name:
        return False
    if name.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


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


