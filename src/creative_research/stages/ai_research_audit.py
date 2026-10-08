"""Read-only preflight over real Lab sources; zero Gemini/API calls."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from creative_research.ai_research import (
    ALLOWED_MODELS,
    DEFAULT_MODEL,
    LabCorpus,
    MAX_INPUT_CHARS,
    MODEL_INSTRUCTIONS,
    ResearchValidationError,
)
from creative_research.pathing import project_root


def audit_ai_readiness(workspace: Path) -> dict[str, Any]:
    corpus = LabCorpus(workspace)
    queue = corpus.lab.get("review", {})
    sources = {}
    for row in queue.get("items", []) + queue.get("reviewed_items", []):
        kind = row.get("review_source_type")
        identifier = row.get("review_source_id")
        if kind and identifier:
            sources[(kind, identifier)] = row
    all_sources = set(sources)
    all_sources.update(
        ("hypothesis", hypothesis_id)
        for hypothesis_id in corpus.strategy_index
    )
    all_sources.update(
        ("family", family_id)
        for family_id, row in corpus.family_index.items()
        if int(row.get("member_count") or 0) > 1
    )
    targets = [
        ("draft_playbook", "operator", corpus.operator_id),
        ("stress_test", "operator", corpus.operator_id),
    ] + [
        ("investigate", kind, identifier)
        for (kind, identifier) in sorted(all_sources)
    ]
    results = []
    errors = []
    for mode, source_type, source_id in targets:
        try:
            packet = corpus.packet(mode, source_type, source_id)
            payload = MODEL_INSTRUCTIONS + "\n\nUNTRUSTED EVIDENCE JSON:\n" + json.dumps(
                packet, ensure_ascii=False, separators=(",", ":"), default=str
            )
            refs = {
                item["evidence_ref"] for item in packet["source_registry"]
            }
            missing_flow_refs = sorted({
                ref
                for flow in packet["selected_flows"]
                for ref in (flow["origin_post_ref"], flow["receiving_post_ref"])
                if ref not in refs
            })
            has_source_posts = any(
                ref.startswith("post:") for ref in refs
            )
            issues = []
            if len(payload) > MAX_INPUT_CHARS:
                issues.append("packet_exceeds_char_budget")
            if missing_flow_refs:
                issues.append("selected_flow_missing_source_post")
            if not has_source_posts:
                issues.append("no_direct_post_sources")
            if (source_type == "family"
                    and (packet.get("family_identity") or {}).get("member_sample_truncated")):
                issues.append("family_identity_member_sample_truncated")
            status = "fail" if issues else "pass"
            entry = {
                "mode": mode, "source_type": source_type,
                "source_id": source_id, "status": status,
                "evidence_count": len(refs),
                "selected_flow_pairs": len(packet["selected_flows"]),
                "available_flow_pairs": packet["sampling"]["available_flow_pairs"],
                "prompt_chars": len(payload),
                "max_prompt_chars": MAX_INPUT_CHARS,
                "missing_flow_refs": missing_flow_refs[:20],
                "issues": issues,
            }
        except ResearchValidationError as exc:
            status = "fail"
            entry = {
                "mode": mode, "source_type": source_type,
                "source_id": source_id, "status": "fail",
                "issues": [str(exc)],
            }
        results.append(entry)
        if status == "fail":
            errors.append(entry)
    return {
        "schema_version": "ai-research-readiness-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "operator_id": corpus.operator_id,
        "status": "pass" if not errors else "fail",
        "targets_checked": len(results),
        "targets_ready": len(results) - len(errors),
        "targets_failed": len(errors),
        "results": results,
        "scope": (
            "Retrieval completeness and boundedness only. "
            "Does not call Gemini or certify semantic accuracy."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline preflight for AI Research Copilot evidence retrieval."
    )
    parser.add_argument(
        "--workspace", default="data/07_exports/operator-intelligence"
    )
    parser.add_argument(
        "--out", default="data/07_exports/operator-intelligence/ai_research_readiness.json"
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser()
    if not workspace.is_absolute():
        workspace = project_root() / workspace
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = project_root() / out
    report = audit_ai_readiness(workspace.resolve())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        key: value for key, value in report.items() if key != "results"
    }, indent=2))
    print(f"Report: {out}")
    if args.strict and report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
