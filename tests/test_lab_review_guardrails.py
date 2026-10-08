from __future__ import annotations

import http.server
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from creative_research.stages.intelligence import (
    _make_handler,
    review_request_error,
    review_source_in_queue,
)


def test_review_validation_requires_notes_and_confirmation() -> None:
    assert review_request_error({"decision": "approve"}) == "review_note_required"
    assert review_request_error(
        {"decision": "approve", "note": "I inspected posts"}
    ) == "evidence_confirmation_required"
    assert review_request_error({
        "decision": "approve",
        "note": "I inspected source and counter posts",
        "evidence_inspected": True,
    }) is None
    assert review_request_error({
        "decision": "hold", "note": "Need larger sample",
    }) is None


def test_review_allowlist_does_not_accept_arbitrary_claim_ids(tmp_path: Path) -> None:
    (tmp_path / "lab.json").write_text(
        json.dumps({"review": {"items": [
            {"review_source_type": "hypothesis", "review_source_id": "STR1"}
        ]}}),
        encoding="utf-8",
    )
    assert review_source_in_queue(tmp_path, "hypothesis", "STR1")
    assert not review_source_in_queue(tmp_path, "hypothesis", "FAKE")
    assert not review_source_in_queue(tmp_path, "family", "STR1")


def test_lab_review_endpoint_enforces_proof_before_persisting(tmp_path: Path) -> None:
    (tmp_path / "lab.json").write_text(
        json.dumps({"review": {"items": [
            {"review_source_type": "hypothesis", "review_source_id": "STR1"}
        ]}}),
        encoding="utf-8",
    )
    reviews_path = tmp_path / "reviews.toml"
    handler = _make_handler(
        root=tmp_path,
        reviews_path=reviews_path,
        read_only=False,
        media_records={},
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def submit(source_id: str, inspected: bool, note: str) -> tuple[int, str]:
        raw = json.dumps({
            "source_type": "hypothesis",
            "source_id": source_id,
            "decision": "approve",
            "note": note,
            "evidence_inspected": inspected,
            "rebuild": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/review",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    try:
        assert submit("STR1", False, "Checked support and counter posts")[0] == 400
        assert submit("FAKE", True, "Checked support and counter posts")[0] == 404
        assert not reviews_path.exists()
        status, body = submit("STR1", True, "Checked support and counter posts")
        assert status == 200
        assert json.loads(body)["review_saved"] is True
        assert "STR1" in reviews_path.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
