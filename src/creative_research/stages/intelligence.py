#!/usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import http.server
import json
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from creative_research.intelligence_workspace import validate_intelligence_workspace
from creative_research.knowledge_reviews import (
    KnowledgeReview,
    upsert_knowledge_reviews,
)
from creative_research.pathing import project_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the local Operator Intelligence Lab."
    )
    parser.add_argument("--dir", default="data/07_exports/operator-intelligence")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument(
        "--reviews",
        default="config/knowledge_reviews.toml",
        help="Local human-review registry written by Insight Review.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable review mutations/rebuild actions.",
    )
    return parser


def resolve_intelligence_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return path.resolve()


def resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return path.resolve()


def _json_response(
    handler: http.server.SimpleHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def _make_handler(
    *,
    root: Path,
    reviews_path: Path,
    read_only: bool,
) -> type[http.server.SimpleHTTPRequestHandler]:
    base = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(root),
    )

    class LabHandler(base.func):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/review":
                _json_response(self, 404, {"error": "not_found"})
                return
            if read_only:
                _json_response(
                    self,
                    403,
                    {"error": "lab_is_read_only"},
                )
                return

            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 65536:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request_size"},
                )
                return

            try:
                payload = json.loads(
                    self.rfile.read(length).decode("utf-8")
                )
            except (UnicodeDecodeError, json.JSONDecodeError):
                _json_response(
                    self,
                    400,
                    {"error": "invalid_json"},
                )
                return
            if not isinstance(payload, dict):
                _json_response(
                    self,
                    400,
                    {"error": "invalid_payload"},
                )
                return

            source_type = str(
                payload.get("source_type") or ""
            ).strip()
            source_id = str(payload.get("source_id") or "").strip()
            decision = str(payload.get("decision") or "").strip().lower()
            note = str(payload.get("note") or "").strip() or None
            reviewed_by = (
                str(payload.get("reviewed_by") or "").strip() or None
            )

            if source_type not in {
                "hypothesis",
                "family",
                "playbook_sources",
            }:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_source_type"},
                )
                return
            if not source_id:
                _json_response(
                    self,
                    400,
                    {"error": "missing_source_id"},
                )
                return
            if decision not in {"approve", "reject", "hold"}:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_decision"},
                )
                return

            review = KnowledgeReview(
                source_type=source_type,
                source_id=source_id,
                decision=decision,
                note=note,
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(UTC).isoformat(),
            )
            upsert_knowledge_reviews(reviews_path, [review])

            should_rebuild = payload.get("rebuild", True) is not False
            rebuild: dict[str, Any] | None = None
            if should_rebuild:
                command = [
                    sys.executable,
                    "-m",
                    "creative_research.stages.intelligence_build",
                    "--from-stage",
                    "knowledge",
                    "--force",
                    "--reviews",
                    str(reviews_path),
                    "--workspace-out",
                    str(root),
                    "--quality-out",
                    str(root / "quality_report.json"),
                    "--report",
                    str(root / "pipeline_report.json"),
                ]
                completed = subprocess.run(
                    command,
                    cwd=str(project_root()),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                rebuild = {
                    "returncode": completed.returncode,
                    "stdout_tail": completed.stdout[-6000:],
                    "stderr_tail": completed.stderr[-6000:],
                }
                if completed.returncode != 0:
                    _json_response(
                        self,
                        500,
                        {
                            "error": "review_saved_rebuild_failed",
                            "review_saved": True,
                            "review": {
                                "source_type": source_type,
                                "source_id": source_id,
                                "decision": decision,
                            },
                            "rebuild": rebuild,
                        },
                    )
                    return

            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "review_saved": True,
                    "review": {
                        "source_type": source_type,
                        "source_id": source_id,
                        "decision": decision,
                    },
                    "rebuild": rebuild,
                },
            )

    return LabHandler


def main() -> None:
    args = build_parser().parse_args()
    root = resolve_intelligence_dir(args.dir)
    reviews_path = resolve_project_path(args.reviews)
    missing = validate_intelligence_workspace(root)
    if missing:
        rendered = "\n".join(f"  - {name}" for name in missing)
        raise SystemExit(
            f"Operator Intelligence Lab is not ready: {root}\n"
            f"Missing required files:\n{rendered}\n\n"
            "Build it first with creative-research build-intelligence-workspace."
        )

    handler = _make_handler(
        root=root,
        reviews_path=reviews_path,
        read_only=args.read_only,
    )
    server = http.server.ThreadingHTTPServer(
        (args.host, args.port),
        handler,
    )
    actual_port = int(server.server_address[1])
    browser_host = (
        "127.0.0.1"
        if args.host in {"0.0.0.0", "::"}
        else args.host
    )
    url = f"http://{browser_host}:{actual_port}/"
    print(f"Operator Intelligence Lab: {root}")
    print(f"Serving:                   {url}")
    print(
        "Review actions:            "
        + ("disabled" if args.read_only else f"enabled → {reviews_path}")
    )
    print("Press Ctrl+C to stop.")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
