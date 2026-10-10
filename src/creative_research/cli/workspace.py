from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from creative_research.analysis.validation import validate_master
from creative_research.constants import DEFAULT_MASTER_PATH, WORKSPACE_DIRS
from creative_research.infrastructure import workspace
from creative_research.infrastructure.paths import project_root
from creative_research.infrastructure.storage import read_table


def cmd_init(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="creative-research init")
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args(args or [])
    root = project_root()
    workspace.initialize_workspace(root)
    if ns.json:
        print(json.dumps({"project": str(root), "directories": WORKSPACE_DIRS}))
    else:
        print(f"Workspace initialized: {root}")
        for rel in WORKSPACE_DIRS:
            print(f"  {rel}")
    return 0


def cmd_doctor(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="creative-research doctor")
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args(args or [])
    checks = workspace.doctor_checks()
    width = max(len(name) for name, _, _, _ in checks)
    hard_fail = False
    if ns.json:
        hard_fail = any(required and not ok for _, ok, _, required in checks)
        print(
            json.dumps(
                {
                    "ok": not hard_fail,
                    "checks": [
                        {"name": name, "ok": ok, "detail": detail, "required": required}
                        for name, ok, detail, required in checks
                    ],
                }
            )
        )
        return 1 if hard_fail else 0
    print("Creative Research doctor\n")
    for name, ok, detail, required in checks:
        marker = "OK" if ok else ("!!" if required else "--")
        print(f"{marker:>2}  {name:<{width}}  {detail}")
        if required and not ok:
            hard_fail = True

    print("\nNotes:")
    print("- APIFY_TOKEN is needed only for `scrape` (and rare media fallback).")
    print("- GEMINI_API_KEY is needed only for Vision stages.")
    print("- ffprobe is optional but improves video metadata.")
    return 1 if hard_fail else 0


def cmd_adopt(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="creative-research adopt",
        description="Adopt existing completed outputs without re-running expensive stages.",
    )
    parser.add_argument("--selected")
    parser.add_argument("--media")
    parser.add_argument("--slides-manifest")
    parser.add_argument("--video-media")
    parser.add_argument("--slides-vision")
    parser.add_argument("--video-vision")
    parser.add_argument("--master")
    parser.add_argument(
        "--apify",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Adopt an immutable Apify scrape run; repeat for multiple runs.",
    )
    parser.add_argument("--mode", choices=["symlink", "copy"], default="symlink")
    parser.add_argument("--replace", action="store_true")
    ns = parser.parse_args(args)

    root = project_root()
    requests = [
        (ns.selected, root / "data/01_selected/targets"),
        (ns.media, root / "data/02_media/tiktok"),
        (ns.slides_manifest, root / "data/03_manifests/slides"),
        (ns.video_media, root / "data/03_video_media"),
        (ns.slides_vision, root / "data/04_vision/slides"),
        (ns.video_vision, root / "data/04_vision/videos"),
        (ns.master, root / "data/05_master"),
    ]

    for item in ns.apify:
        if "=" not in item:
            raise SystemExit("--apify expects NAME=PATH")
        name, src = item.split("=", 1)
        name = name.strip()
        if name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.@-]+", name):
            raise ValueError(f"Invalid Apify run name: {name!r}")
        requests.append((src, root / "data/00_raw/apify" / name))

    workspace.adopt_outputs(requests, mode=ns.mode, replace=ns.replace)

    return cmd_status([])


def cmd_status(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="creative-research status")
    parser.add_argument("--json", action="store_true", dest="as_json")
    ns = parser.parse_args(args)

    root = project_root()
    rows = workspace.status_rows(root)
    if ns.as_json:
        print(json.dumps({"project": str(root), "artifacts": rows}, indent=2))
        return 0

    print(f"Project: {root}\n")
    for row in rows:
        if row["present"]:
            print(f"OK {row['label']:<30} {row['count']:>6}  ({row['path']})")
        else:
            print(f"-- {row['label']:<30} missing  ({row['path']})")
    return 0


def cmd_validate(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="creative-research validate",
        description="Validate creative_master schema and core invariants.",
    )
    parser.add_argument(
        "--master",
        default=str(DEFAULT_MASTER_PATH),
        help="Path to creative_master parquet/csv/jsonl.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    ns = parser.parse_args(args)

    path = Path(ns.master).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    path = path.resolve()

    try:
        df = read_table(path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Validation input error: {exc}", file=sys.stderr)
        return 2

    report = validate_master(df)
    payload = {"master": str(path), **report.as_dict()}
    if ns.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        marker = "OK" if report.ok else "FAILED"
        print(f"{marker}: {path}")
        print(f"rows={report.rows} accounts={report.accounts}")
        print(f"content_types={report.content_type_counts}")
        for issue in report.issues:
            print(f"{issue.level.upper():>7} {issue.code}: {issue.message}")
    return 0 if report.ok else 1
