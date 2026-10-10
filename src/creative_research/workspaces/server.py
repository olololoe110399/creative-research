"""Loopback-only HTTP adapters and server lifecycle for local workspaces."""

from __future__ import annotations

import functools
import http.server
import json
import mimetypes
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from creative_research.infrastructure.http import loopback_host, parse_byte_range, respond
from creative_research.infrastructure.local_server import (
    LocalHTTPServer,
    SafeStaticHandler,
    require_loopback,
    serve_local,
)
from creative_research.infrastructure.paths import resolve_path
from creative_research.operating.state import OperatingStore
from creative_research.references.media import local_media_sources_for_post
from creative_research.workspaces.lab import validate_intelligence_workspace
from creative_research.workspaces.operating_api import handle_operating_get, handle_operating_post
from creative_research.workspaces.references import validate_reference_workspace


def make_lab_handler(
    *,
    root: Path,
    read_only: bool,
    media_records: dict[str, dict[str, Any]],
    operating_service: OperatingStore | None = None,
) -> type[http.server.SimpleHTTPRequestHandler]:
    class LabHandler(SafeStaticHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def _serve_local_media(self, kind: str, post_uid: str) -> None:
            record = media_records.get(post_uid)
            if record is None:
                self.send_error(404, "Unknown post")
                return
            source = local_media_sources_for_post(record).get(kind)
            if source is None or not source.is_file():
                self.send_error(404, "Local media unavailable")
                return

            size = int(source.stat().st_size)
            content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            range_header = self.headers.get("Range")
            start = 0
            end = size - 1
            partial = False
            if range_header:
                try:
                    start, end = parse_byte_range(range_header, size)
                    partial = True
                except (TypeError, ValueError):
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

            length = end - start + 1
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header(
                    "Content-Range",
                    f"bytes {start}-{end}/{size}",
                )
            self.end_headers()

            with source.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def do_GET(self) -> None:  # noqa: N802
            if not loopback_host(self):
                respond(self, 403, {"error": "loopback_host_required"})
                return
            parsed = urlparse(self.path)
            if handle_operating_get(self, operating_service):
                return
            parts = parsed.path.strip("/").split("/")
            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "media"
                and parts[2] in {"thumbnail", "video"}
            ):
                self._serve_local_media(
                    parts[2],
                    unquote(parts[3]),
                )
                return
            if parsed.path.startswith("/api/"):
                respond(self, 404, {"error": "not_found"})
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if not loopback_host(self):
                respond(self, 403, {"error": "loopback_host_required"})
                return
            if handle_operating_post(self, operating_service, read_only=read_only):
                return
            respond(self, 404, {"error": "not_found"})

    return LabHandler


def serve_lab(*, directory: str, host: str, port: int, read_only: bool, open_browser: bool) -> None:
    require_loopback(host)
    root = resolve_path(directory)
    missing = validate_intelligence_workspace(root)
    if missing:
        rendered = "\n".join(f"  - {name}" for name in missing)
        raise SystemExit(
            f"Operator Intelligence Lab is not ready: {root}\n"
            f"Missing required files:\n{rendered}\n\n"
            "Build it first with creative-research build-intelligence-workspace."
        )

    evidence_path = root / "evidence.json"
    try:
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        evidence_payload = {}
    media_records = {
        str(row.get("post_uid")): row
        for row in evidence_payload.get("posts", [])
        if isinstance(row, dict) and row.get("post_uid")
    }

    handler = make_lab_handler(
        root=root,
        read_only=read_only,
        media_records=media_records,
        operating_service=OperatingStore(root),
    )
    server = LocalHTTPServer(
        (host, port),
        handler,
    )
    actual_port = int(server.server_address[1])
    browser_host = f"[{host}]" if ":" in host else host
    url = f"http://{browser_host}:{actual_port}/"
    print(f"Operator Intelligence Lab: {root}")
    print(f"Serving:                   {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    serve_local(server)


def serve_references(*, directory: str, host: str, port: int, open_browser: bool) -> None:
    require_loopback(host)
    root = resolve_path(directory)
    missing = validate_reference_workspace(root)
    if missing:
        rendered = "\n".join(f"  - {name}" for name in missing)
        raise SystemExit(
            f"Reference Workspace is not ready: {root}\n"
            f"Missing required files:\n{rendered}\n\n"
            "Build it first with `creative-research extract-references ...`."
        )

    handler = functools.partial(SafeStaticHandler, directory=str(root))
    server = LocalHTTPServer((host, port), handler)
    actual_port = int(server.server_address[1])
    browser_host = f"[{host}]" if ":" in host else host
    url = f"http://{browser_host}:{actual_port}/"
    print(f"References: {root}")
    print(f"Serving:    {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    serve_local(server)
