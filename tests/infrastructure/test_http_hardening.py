from __future__ import annotations

import functools
import io
import json
import threading
import urllib.error
import urllib.request
from email.message import Message

import pytest

from creative_research.infrastructure.http import (
    loopback_host,
    parse_byte_range,
    read_json_request,
    same_origin_json_request,
)
from creative_research.infrastructure.local_server import (
    LocalHTTPServer,
    SafeStaticHandler,
    require_loopback,
    serve_local,
)


class Request:
    def __init__(self, body=b"{}", length=None):
        self.headers = Message()
        self.headers["Content-Length"] = str(len(body) if length is None else length)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass


@pytest.mark.parametrize(
    "body,error",
    [
        (b"null", "invalid_payload"),
        (b"[]", "invalid_payload"),
        (b"{bad", "invalid_json"),
        (b"\xff\xff", "invalid_json"),
    ],
)
def test_json_body_rejects_malformed_payload(body, error) -> None:
    handler = Request(body)
    assert read_json_request(handler, max_bytes=100) is None
    assert handler.status == 400
    assert json.loads(handler.wfile.getvalue())["error"] == error


@pytest.mark.parametrize("length", ["invalid", -1, 0, 1000])
def test_invalid_lengths_are_rejected_before_reading_body(length) -> None:
    handler = Request(length=length)
    assert read_json_request(handler, max_bytes=100) is None
    assert handler.rfile.tell() == 0
    assert handler.status == 400


def test_short_reads_duplicate_lengths_and_chunked_bodies_are_rejected() -> None:
    handler = Request(length=5)
    assert read_json_request(handler, max_bytes=100) is None
    assert json.loads(handler.wfile.getvalue())["error"] == "incomplete_request_body"
    for extra in ("Content-Length", "Transfer-Encoding"):
        handler = Request()
        handler.headers[extra] = "2" if extra == "Content-Length" else "chunked"
        assert read_json_request(handler, max_bytes=100) is None
        assert handler.rfile.tell() == 0


def test_body_timeout_is_actionable_and_object_body_is_accepted() -> None:
    handler = Request(b'{"ok":true}')
    assert read_json_request(handler, max_bytes=100) == {"ok": True}

    class TimedOut:
        def read(self, size):
            raise TimeoutError

    handler = Request()
    handler.rfile = TimedOut()
    assert read_json_request(handler, max_bytes=100) is None
    assert handler.status == 408


def test_malformed_host_and_origin_fail_closed() -> None:
    handler = Request()
    handler.headers["Host"] = "[bad-ipv6"
    assert not loopback_host(handler)
    handler.headers["Content-Type"] = "application/json"
    handler.headers["Origin"] = "http://[bad-ipv6"
    assert not same_origin_json_request(handler)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("bytes=2-5", (2, 5)),
        ("bytes=2-", (2, 9)),
        ("bytes=-3", (7, 9)),
        ("bytes=-20", (0, 9)),
        ("bytes=0-99", (0, 9)),
    ],
)
def test_byte_ranges(header, expected) -> None:
    assert parse_byte_range(header, 10) == expected


@pytest.mark.parametrize(
    "header",
    [
        "bytes=10-",
        "bytes=9-8",
        "bytes=-0",
        "bytes=-",
        "bytes=0-2,4-6",
        "other=0-1",
        "bytes=-1-3",
        "bytes=a-b",
    ],
)
def test_invalid_byte_ranges_are_not_silently_clamped(header) -> None:
    with pytest.raises(ValueError):
        parse_byte_range(header, 10)
    with pytest.raises(ValueError):
        parse_byte_range("bytes=0-1", 0)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "example.test"])
def test_local_server_rejects_public_binds(host) -> None:
    with pytest.raises(ValueError, match="authentication"):
        require_loopback(host)


def test_static_server_confines_files_and_hides_private_paths(tmp_path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "index.html").write_text("safe")
    (root / ".env").write_text("private")
    (root / "directory").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    (root / "escape.txt").symlink_to(outside)
    monkeypatch.setenv("CREATIVE_RESEARCH_SERVER_REQUEST_TIMEOUT", "1")
    server = LocalHTTPServer(
        ("127.0.0.1", 0), functools.partial(SafeStaticHandler, directory=str(root))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(base + "/", timeout=3) as response:
            assert response.read() == b"safe"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        for path in ("/.env", "/%2eenv", "/escape.txt", "/directory/"):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + path, timeout=3)
            assert error.value.code == 403
        request = urllib.request.Request(base, headers={"Host": "evil.test"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=3)
        assert error.value.code == 403
        assert server.request_timeout == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_shutdown_closes_server_and_restores_sigterm_handler(monkeypatch) -> None:
    import signal

    previous = signal.getsignal(signal.SIGTERM)

    class Server:
        closed = False

        def serve_forever(self, **kwargs):
            signal.raise_signal(signal.SIGTERM)

        def server_close(self):
            self.closed = True

    server = Server()
    with pytest.raises(KeyboardInterrupt):
        serve_local(server)
    assert server.closed
    assert signal.getsignal(signal.SIGTERM) == previous


def test_shutdown_restores_signal_even_when_close_fails() -> None:
    import signal

    previous = signal.getsignal(signal.SIGTERM)

    class Server:
        def serve_forever(self, **kwargs):
            pass

        def server_close(self):
            raise OSError("close failed")

    with pytest.raises(OSError, match="close failed"):
        serve_local(Server())
    assert signal.getsignal(signal.SIGTERM) == previous
