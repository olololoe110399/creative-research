"""Exercise local Lab AI routes without paid model calls or review writes."""
from __future__ import annotations

import http.server
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from creative_research.ai_research import AIResearchService
from creative_research.stages.intelligence import _make_handler


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    payloads = {
        "lab": {
            "research_brief": {
                "operator": {"operator_id": "OP1"},
                "stats": {"posts": 2, "families": 1},
                "guardrails": [], "key_findings": [],
            },
            "review": {"items": [{
                "review_source_type": "family", "review_source_id": "F1",
            }], "reviewed_items": []},
            "playbook": {"status": "research_draft"},
        },
        "strategies": {"strategies": []},
        "patterns": {"patterns": []},
        "families": {"families": [{
            "operator_id": "OP1", "family_id": "F1",
            "member_count": 2, "cross_account": True,
            "family_origin_post_uid": "P1",
            "propagation": [{
                "operator_id": "OP1", "family_id": "F1",
                "family_origin_post_uid": "P1", "target_first_post_uid": "P2",
                "origin_account": "A", "target_account": "B",
                "target_outperformed_origin": False,
                "target_vs_origin_views_percentile_delta": -.6,
            }],
        }]},
        "evidence": {"posts": [
            {"post_uid": "P1", "operator_id": "OP1", "account_id": "A",
             "account": "A", "url": "https://example.test/a", "creative": {}},
            {"post_uid": "P2", "operator_id": "OP1", "account_id": "B",
             "account": "B", "url": "https://example.test/b", "creative": {}},
        ]},
        "knowledge": {"knowledge": [], "active": []},
    }
    for name, payload in payloads.items():
        (root / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def _model(_: str) -> dict:
    return {
        "summary": "The family moved across accounts, but causal intent is not known.",
        "proposed_review": "hold",
        "review_rationale": "A family chronology does not establish operator intent.",
        "findings": [{
            "interpretation": "counterexample",
            "statement": "The receiving post did not outperform the originating execution.",
            "evidence_refs": ["family:F1", "post:P2"],
        }],
        "alternative_explanations": ["Cross-posting is possible."],
        "missing_evidence": ["No verified internal testing records."],
        "experiments": [],
    }


def _post(url: str, body: dict, *, headers: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=6) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_ai_http_plan_run_report_origin_and_no_review_mutation(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    review_path = tmp_path / "knowledge_reviews.toml"
    service = AIResearchService(
        root, enabled=True, generator=_model, max_calls=1,
        report_dir=tmp_path / "private_proposals",
    )
    handler = _make_handler(
        root=root, reviews_path=review_path,
        read_only=False, media_records={}, ai_service=service,
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    body = {"mode": "investigate", "source_type": "family", "source_id": "F1"}
    try:
        status, info = _get(base + "/api/ai/status")
        assert status == 200
        assert info["enabled"] and info["configured"]
        assert "GEMINI_API_KEY" not in json.dumps(info)
        status, result = _post(base + "/api/ai/plan", body)
        assert status == 200 and result["plan"]["source_count"] >= 3
        assert service.call_count == 0

        status, result = _post(
            base + "/api/ai/run", body,
            headers={"Origin": "https://attacker.example"},
        )
        assert status == 403
        assert result["error"] == "same_origin_json_required"
        assert service.call_count == 0

        status, result = _post(
            base + "/api/ai/run", body,
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert status == 403
        assert service.call_count == 0

        status, result = _post(base + "/api/ai/run", body)
        assert status == 200
        assert result["report"]["ai_status"] == "proposal_only"
        report_id = result["report"]["request_id"]
        assert service.call_count == 1
        assert not review_path.exists()

        status, saved = _get(base + "/api/ai/report/" + report_id)
        assert status == 200 and saved["request_id"] == report_id
        assert saved["snapshot_is_current"] is True
        status, history = _get(
            base + "/api/ai/history?source_type=family&source_id=F1"
        )
        assert status == 200
        assert len(history["reports"]) == 1
        assert history["reports"][0]["request_id"] == report_id
        status, result = _get(base + "/api/ai/report/..%2f..%2fsecret")
        assert status == 404
        assert result["error"] in {"invalid_report_id", "report_not_found"}
        assert not review_path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ai_http_read_only_refuses_spending(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    service = AIResearchService(root, enabled=True, generator=_model)
    handler = _make_handler(
        root=root, reviews_path=tmp_path / "reviews.toml",
        read_only=True, media_records={}, ai_service=service,
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    body = {"mode": "challenge", "source_type": "family", "source_id": "F1"}
    try:
        status, _ = _post(base + "/api/ai/plan", body)
        assert status == 200
        status, result = _post(base + "/api/ai/run", body)
        assert status == 403 and result["error"] == "ai_disabled_or_read_only"
        assert service.call_count == 0
        status, _ = _post(
            base + "/api/ai/plan", body,
            headers={"Content-Type": "text/plain"},
        )
        assert status == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)



def test_dns_rebinding_host_cannot_read_or_trigger_ai(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    service = AIResearchService(root, enabled=True, generator=_model)
    handler = _make_handler(
        root=root, reviews_path=tmp_path / "reviews.toml",
        read_only=False, media_records={}, ai_service=service,
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    body = {"mode": "investigate", "source_type": "family", "source_id": "F1"}
    try:
        status, result = _post(
            base + "/api/ai/run", body,
            headers={"Host": "attacker.example", "Origin": "http://attacker.example"},
        )
        assert status == 403
        assert result["error"] == "loopback_host_required"
        assert service.call_count == 0
        request = urllib.request.Request(
            base + "/api/ai/status", headers={"Host": "attacker.example"},
        )
        try:
            with urllib.request.urlopen(request, timeout=6):
                pytest.fail("DNS-rebinding host unexpectedly allowed")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
