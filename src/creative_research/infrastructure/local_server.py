"""Bounded local HTTP transport, confined static files and signal-aware cleanup.

This is a single-user developer server, not an authenticated public web service.
"""

from __future__ import annotations

import ipaddress
import logging
import signal
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from os import PathLike
from pathlib import Path
from socket import AF_INET6, socket
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

from creative_research.infrastructure.config import RuntimeSettings
from creative_research.infrastructure.http import loopback_host

logger = logging.getLogger(__name__)


def require_loopback(host: str) -> None:
    try:
        valid = ipaddress.ip_address(host).is_loopback
    except ValueError:
        valid = host.lower() == "localhost"
    if not valid:
        raise ValueError(
            "Local workspaces require --host localhost or 127.0.0.1; public hosting needs authentication and a separate server."
        )


class LocalHTTPServer(ThreadingHTTPServer):
    """Bound concurrent workers and socket reads; reject overload without new threads."""

    daemon_threads = False
    block_on_close = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args and ":" in args[0][0]:
            self.address_family = AF_INET6
        self._workers = threading.BoundedSemaphore(32)
        self.request_timeout = RuntimeSettings.from_environ().server_request_timeout
        super().__init__(*args, **kwargs)

    def get_request(self) -> tuple[socket, Any]:
        connection, address = super().get_request()
        connection.settimeout(self.request_timeout)
        return connection, address

    def process_request(self, request: socket | tuple[bytes, socket], client_address: Any) -> None:
        if not self._workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._workers.release()
            raise

    def process_request_thread(
        self, request: socket | tuple[bytes, socket], client_address: Any
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._workers.release()


class SafeStaticHandler(SimpleHTTPRequestHandler):
    def send_head(self) -> BinaryIO | None:
        if not loopback_host(self):
            self.send_error(403, "Loopback Host required")
            return None
        components = unquote(urlparse(self.path).path).split("/")
        if any(part.startswith(".") for part in components if part):
            self.send_error(403, "Private paths are not served")
            return None
        root = Path(self.directory).resolve()
        target = Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(root):
            self.send_error(403, "Path leaves workspace")
            return None
        return super().send_head()

    def list_directory(self, path: str | PathLike[str]) -> None:
        self.send_error(403, "Directory listing is disabled")
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, message_format: str, *args: Any) -> None:
        logger.debug("http_request", extra={"context": {"message": message_format % args}})


def serve_local(server: LocalHTTPServer) -> None:
    """Close the listener and drain bounded workers on Ctrl+C/SIGTERM."""
    previous = None
    main_thread = threading.current_thread() is threading.main_thread()
    if main_thread:
        previous = signal.getsignal(signal.SIGTERM)

        def terminate(_signum: int, _frame: Any) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        try:
            server.server_close()
        finally:
            if main_thread and previous is not None:
                signal.signal(signal.SIGTERM, previous)
