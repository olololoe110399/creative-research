"""CLI adapters for workspace diagnostics and portable dataset validation."""

from __future__ import annotations

import argparse
import json

from creative_research.capture.validation import validate_dataset
from creative_research.constants import WORKSPACE_DIRS
from creative_research.infrastructure import workspace
from creative_research.infrastructure.paths import project_root, resolve_path


def cmd_init(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="creative-research init")
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args([] if args is None else args)
    root = project_root()
    workspace.initialize_workspace(root)
    payload = {"project": str(root), "directories": WORKSPACE_DIRS}
    print(json.dumps(payload) if ns.json else f"Workspace initialized: {root}")
    return 0


def cmd_doctor(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="creative-research doctor")
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args([] if args is None else args)
    checks = workspace.doctor_checks()
    ok = all(present for _, present, _, required in checks if required)
    payload = {
        "ok": ok,
        "checks": [
            {"name": name, "ok": present, "detail": detail, "required": required}
            for name, present, detail, required in checks
        ],
    }
    if ns.json:
        print(json.dumps(payload))
    else:
        for name, present, detail, _ in checks:
            print(f"{'OK' if present else '--'} {name}: {detail}")
        print("APIFY_TOKEN is needed for scrape; ffprobe is optional for video metadata.")
    return 0 if ok else 1


def cmd_status(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="creative-research status")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run", help="Read durable pipeline status from a run directory")
    ns = parser.parse_args([] if args is None else args)
    if ns.run:
        from creative_research.capture.pipeline import read_run

        state = read_run(resolve_path(ns.run))
        if ns.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
        else:
            print(f"Pipeline {state['run_id']}: {state['status']}")
            for name, stage in state["stages"].items():
                print(f"{name}: {stage['status']} ({stage['attempts']} attempts)")
            if state.get("error"):
                print(state["error"])
        return 0
    rows = workspace.status_rows(project_root())
    if ns.json:
        print(json.dumps({"project": str(project_root()), "artifacts": rows}))
    else:
        for row in rows:
            print(f"{row['label']}: {row['count']} files ({row['path']})")
    return 0


def cmd_validate(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="creative-research validate",
        description="Verify exported dataset integrity without modifying files.",
    )
    parser.add_argument("--dataset", required=True, help="Extracted dataset directory")
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args([] if args is None else args)
    path = resolve_path(ns.dataset)
    report = {"dataset": str(path), **validate_dataset(path)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1
