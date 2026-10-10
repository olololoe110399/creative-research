from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from creative_research.cli import app as cli
from creative_research.cli.commands.lab import build_parser
from creative_research.infrastructure.local_server import LocalHTTPServer
from creative_research.workspaces.server import make_lab_handler


@pytest.mark.parametrize("command", ["intelligence", "ai-research-audit", "version", "help"])
def test_internal_commands_are_not_public_aliases(command, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.execute([command]) == 2
    assert "Unknown command" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "flag", ["--ai-enabled", "--ai-model", "--ai-max-calls", "--enable-legacy-review-actions"]
)
def test_lab_has_no_retired_service_flags(flag):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args([flag])
    assert error.value.code == 2


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_removed_endpoints_cannot_write_or_call_models(tmp_path, method):
    server = LocalHTTPServer(
        ("127.0.0.1", 0),
        make_lab_handler(root=tmp_path, read_only=False, media_records={}),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for path in ("/api/review", "/api/experiments", "/api/ai/status", "/api/ai/research"):
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                method=method,
                data=b"{}" if method == "POST" else None,
                headers={"Content-Type": "application/json"},
            )
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=3)
            assert error.value.code == 404
            assert json.loads(error.value.read()) == {"error": "not_found"}
        assert list(tmp_path.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
