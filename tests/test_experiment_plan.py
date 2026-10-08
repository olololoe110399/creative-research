from __future__ import annotations

import http.server
import json
import stat
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from creative_research.experiment_plan import ExperimentPlanError, ExperimentPlanStore
from creative_research.stages.intelligence import _make_handler


def _lab(tmp_path: Path) -> Path:
    workspace = tmp_path / "data/07_exports/operator-intelligence"
    workspace.mkdir(parents=True)
    (workspace / "lab.json").write_text(json.dumps({
        "research_intelligence": {
            "operator_id": "OP1",
            "experiment_candidates": [
                {
                    "key": "explore",
                    "title": "Explore a core idea",
                    "basis": "inferred",
                    "related_hypothesis_id": "STR1",
                    "application_exercise": "Try a concept on your own profile.",
                    "experiment_not_proven": True,
                },
                {
                    "key": "measure",
                    "title": "Measure pilot outcomes",
                    "basis": "method_only",
                    "experiment_not_proven": True,
                },
            ],
        }
    }), encoding="utf-8")
    return workspace


def test_first_party_plan_is_private_scoped_and_is_not_operator_approval(tmp_path: Path) -> None:
    workspace = _lab(tmp_path)
    store = ExperimentPlanStore(workspace)
    assert store.view()["selected_count"] == 0
    outcome = store.mutate(key="explore", action="add")
    assert outcome["selected_count"] == 1
    entry = outcome["entries"][0]
    assert entry["evidence_not_operator_approval"] is True
    assert entry["candidate"]["basis"] == "inferred"
    assert entry["is_current"]
    assert store._path("OP1").exists()
    assert stat.S_IMODE(store._path("OP1").stat().st_mode) == 0o600
    record = store.mutate(
        key="explore", action="progress", state="evaluated",
        notes="One account performed worse; another remained near baseline.",
        metric_observed="account-relative percentile 0.23 and 0.52",
    )["entries"][0]
    assert record["state"] == "evaluated"
    assert record["metric_observed"].startswith("account-relative")
    assert record["evidence_not_operator_approval"]
    assert store.mutate(key="explore", action="remove")["selected_count"] == 0


def test_plan_rejects_unknown_and_stale_candidates(tmp_path: Path) -> None:
    workspace = _lab(tmp_path)
    store = ExperimentPlanStore(workspace)
    with pytest.raises(ExperimentPlanError, match="unknown_experiment_candidate"):
        store.mutate(key="FAKE", action="add")
    store.mutate(key="explore", action="add")
    p = workspace / "lab.json"
    document = json.loads(p.read_text(encoding="utf-8"))
    document["research_intelligence"]["experiment_candidates"][0][
        "application_exercise"
    ] = "Changed hypothesis evidence; recheck this experiment."
    p.write_text(json.dumps(document), encoding="utf-8")
    assert store.view()["entries"][0]["needs_recheck"]
    with pytest.raises(
        ExperimentPlanError, match="stale_experiment_requires_reselection"
    ):
        store.mutate(key="explore", action="progress", state="running")
    assert store.mutate(key="explore", action="remove")["selected_count"] == 0


def test_plan_does_not_mix_different_operator_scopes(tmp_path: Path) -> None:
    workspace = _lab(tmp_path)
    store = ExperimentPlanStore(workspace)
    store.mutate(key="explore", action="add")
    path = workspace / "lab.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["research_intelligence"]["operator_id"] = "OP2"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.view()["entries"] == []
    assert store._path("OP2") != store._path("OP1")


def _request(
    base: str, action: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    url = base + "/api/experiments"
    kwargs = {}
    if action is not None:
        kwargs["data"] = json.dumps(action).encode("utf-8")
    request = urllib.request.Request(
        url, headers={"Content-Type": "application/json", **(headers or {})}, **kwargs
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_experiment_endpoints_require_same_origin_and_read_only(tmp_path: Path) -> None:
    workspace = _lab(tmp_path)
    store = ExperimentPlanStore(workspace)
    handler = _make_handler(
        root=workspace, reviews_path=tmp_path/"reviews.toml",
        read_only=False, media_records={}, experiment_service=store,
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, data = _request(url)
        assert status == 200
        assert data["selected_count"] == 0
        status, _ = _request(
            url, {"key": "explore", "action": "add"},
            {"Origin": "http://attacker.invalid"},
        )
        assert status == 403
        assert store.view()["selected_count"] == 0
        status, _ = _request(
            url, {"key": "explore", "action": "add"},
            {"Host": "attacker.invalid"},
        )
        assert status == 403
        status, data = _request(url, {"key": "explore", "action": "add"})
        assert status == 200 and data["plan"]["selected_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    handler_read_only = _make_handler(
        root=workspace, reviews_path=tmp_path/"reviews.toml",
        read_only=True, media_records={}, experiment_service=store,
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_read_only)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        new_url = f"http://127.0.0.1:{server.server_address[1]}"
        assert _request(new_url)[1]["selected_count"] == 1
        assert _request(
            new_url, {"key": "explore", "action": "remove"}
        )[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
