#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import ipaddress
import json
import mimetypes
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from creative_research.ai_endpoints import (
    handle_ai_get,
    handle_ai_post,
    same_origin_json_request,
)
from creative_research.ai_research import AIResearchService, ALLOWED_MODELS, DEFAULT_MODEL
from creative_research.intelligence_workspace import validate_intelligence_workspace
from creative_research.knowledge_reviews import (
    KnowledgeReview,
    upsert_knowledge_reviews,
)
from creative_research.reference_media import local_media_sources_for_post
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
        "--ai-enabled", action="store_true",
        help="Opt in to paid Gemini research requests from the Lab.",
    )
    parser.add_argument(
        "--ai-model", choices=sorted(ALLOWED_MODELS), default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--ai-max-calls", type=int, default=12,
        help="Maximum paid model attempts per local Lab server process (1–100).",
    )
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


def review_request_error(payload: dict[str, Any]) -> str | None:
    """Validate explicit evidence review; a click alone is not human validation."""
    note = str(payload.get("note") or "").strip()
    if len(note) < 10:
        return "review_note_required"
    if payload.get("decision") == "approve" and payload.get("evidence_inspected") is not True:
        return "evidence_confirmation_required"
    return None


def review_source_in_queue(
    workspace: Path,
    source_type: str,
    source_id: str,
) -> bool:
    """Prevent arbitrary IDs from being given an approval outside the review queue."""
    try:
        lab = json.loads((workspace / "lab.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(
        isinstance(item, dict)
        and item.get("review_source_type") == source_type
        and item.get("review_source_id") == source_id
        for item in (
            lab.get("review", {}).get("items", [])
            + lab.get("review", {}).get("reviewed_items", [])
        )
    )


def _make_handler(
    *,
    root: Path,
    reviews_path: Path,
    read_only: bool,
    media_records: dict[str, dict[str, Any]],
    ai_service: AIResearchService | None = None,
) -> type[http.server.SimpleHTTPRequestHandler]:
    class LabHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

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
            content_type = (
                mimetypes.guess_type(source.name)[0]
                or "application/octet-stream"
            )
            range_header = self.headers.get("Range")
            start = 0
            end = size - 1
            partial = False
            if range_header and range_header.startswith("bytes="):
                raw = range_header[6:].split(",", 1)[0].strip()
                try:
                    left, right = raw.split("-", 1)
                    if left:
                        start = int(left)
                        end = int(right) if right else size - 1
                    elif right:
                        suffix = int(right)
                        start = max(0, size - suffix)
                    start = max(0, min(start, size - 1))
                    end = max(start, min(end, size - 1))
                    partial = True
                except (TypeError, ValueError):
                    self.send_error(416, "Invalid byte range")
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
            parsed = urlparse(self.path)
            if handle_ai_get(self, ai_service, self.path):
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
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if handle_ai_post(self, ai_service, read_only=read_only):
                return
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
            if not same_origin_json_request(self):
                _json_response(self, 403, {"error": "same_origin_json_required"})
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
            error = review_request_error(payload)
            if error:
                _json_response(self, 400, {"error": error})
                return
            if not review_source_in_queue(root, source_type, source_id):
                _json_response(self, 404, {"error": "unknown_review_source"})
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
    if args.ai_enabled:
        if args.read_only:
            raise SystemExit("Cannot enable AI model calls in --read-only mode.")
        try:
            is_loopback = ipaddress.ip_address(args.host).is_loopback
        except ValueError:
            is_loopback = args.host.lower() == "localhost"
        if not is_loopback:
            raise SystemExit("AI model calls require --host localhost / loopback.")
    ai_service = AIResearchService(
        root,
        enabled=args.ai_enabled,
        model=args.ai_model,
        max_calls=args.ai_max_calls,
    )
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
        evidence_payload = json.loads(
            evidence_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        evidence_payload = {}
    media_records = {
        str(row.get("post_uid")): row
        for row in evidence_payload.get("posts", [])
        if isinstance(row, dict) and row.get("post_uid")
    }

    handler = _make_handler(
        root=root,
        reviews_path=reviews_path,
        read_only=args.read_only,
        media_records=media_records,
        ai_service=ai_service,
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
    print(
        "AI Research Copilot:      "
        + (
            f"enabled ({args.ai_model}, {args.ai_max_calls} max calls)"
            if args.ai_enabled else "disabled (enable with --ai-enabled)"
        )
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
