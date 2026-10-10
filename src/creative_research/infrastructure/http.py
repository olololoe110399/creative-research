"""Bounded JSON requests, media ranges and localhost origin checks."""

from __future__ import annotations

import ipaddress
import json
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse


def parse_byte_range(header: str, size: int) -> tuple[int, int]:
    """One valid inclusive byte range; reject unsupported multipart/empty ranges."""
    if size <= 0 or not header.startswith("bytes=") or "," in header:
        raise ValueError("Invalid byte range")
    left, separator, right = header[6:].partition("-")
    if not separator or not (left or right):
        raise ValueError("Invalid byte range")
    if left:
        if not left.isdecimal() or (right and not right.isdecimal()):
            raise ValueError("Invalid byte range")
        start = int(left)
        end = int(right) if right else size - 1
        if start >= size or end < start:
            raise ValueError("Unsatisfiable byte range")
        return start, min(end, size - 1)
    if not right.isdecimal() or int(right) <= 0:
        raise ValueError("Invalid suffix byte range")
    return max(0, size - int(right)), size - 1


def read_json_request(
    handler: BaseHTTPRequestHandler, *, max_bytes: int, min_bytes: int = 2
) -> dict[str, Any] | None:
    """Read one bounded JSON object, writing a precise error response on failure."""
    try:
        lengths = handler.headers.get_all("Content-Length", [])
        size = int(lengths[0]) if len(lengths) == 1 else 0
    except (ValueError, TypeError):
        size = 0
    if handler.headers.get("Transfer-Encoding") or not min_bytes <= size <= max_bytes:
        respond(handler, 400, {"error": "invalid_request_size"})
        return None
    try:
        raw = handler.rfile.read(size)
    except TimeoutError:
        respond(handler, 408, {"error": "request_body_timeout"})
        return None
    if len(raw) != size:
        respond(handler, 400, {"error": "incomplete_request_body"})
        return None
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        respond(handler, 400, {"error": "invalid_json"})
        return None
    if not isinstance(body, dict):
        respond(handler, 400, {"error": "invalid_payload"})
        return None
    return body


def loopback_host(handler: BaseHTTPRequestHandler) -> bool:
    """Block DNS-rebinding hosts even when Origin and Host happen to match."""
    try:
        name = urlparse("http://" + handler.headers.get("Host", "")).hostname
    except ValueError:
        return False
    if not name:
        return False
    if name.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def same_origin_json_request(handler: BaseHTTPRequestHandler) -> bool:
    """Reject cross-site browser requests that could mutate local state."""
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return False
    if handler.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        return False
    origin = handler.headers.get("Origin")
    if origin:
        try:
            parsed = urlparse(origin)
        except ValueError:
            return False
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
