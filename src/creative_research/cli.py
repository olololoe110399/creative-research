from __future__ import annotations

import argparse
import importlib.util
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

from creative_research import __version__
from creative_research.constants import DEFAULT_MASTER_PATH, WORKSPACE_DIRS
from creative_research.pathing import project_root

COMMANDS = {
    "scrape": "creative_research.stages.scrape",
    "select-accounts": "creative_research.stages.select_accounts",
    "prepare-media": "creative_research.stages.prepare_media",
    "manifest-slides": "creative_research.stages.manifest_slides",
    "vision-slides": "creative_research.stages.vision_slides",
    "download-videos": "creative_research.stages.download_videos",
    "vision-videos": "creative_research.stages.vision_videos",
    "build-master": "creative_research.stages.build_master",
    "build-warehouse": "creative_research.stages.build_warehouse",
    "analyze-performance": "creative_research.stages.analyze_performance",
    "analyze-cadence": "creative_research.stages.analyze_cadence",
    "build-families": "creative_research.stages.build_families",
    "calibrate-families": "creative_research.stages.calibrate_families",
    "preview-families-v2": "creative_research.stages.preview_families_v2",
    "judge-family-candidates": "creative_research.stages.judge_family_candidates",
    "analyze-propagation": "creative_research.stages.analyze_propagation",
    "analyze-timeline": "creative_research.stages.analyze_timeline",
    "discover-patterns": "creative_research.stages.discover_patterns",
    "infer-strategies": "creative_research.stages.infer_strategies",
    "promote-knowledge": "creative_research.stages.promote_knowledge",
    "review-knowledge": "creative_research.stages.review_knowledge",
    "build-intelligence-workspace": "creative_research.stages.build_intelligence_workspace",
    "intelligence": "creative_research.stages.intelligence",
    "lab": "creative_research.stages.intelligence",
    "intelligence-build": "creative_research.stages.intelligence_build",
    "quality-audit": "creative_research.stages.quality_audit",
    "outcome-audit": "creative_research.stages.outcome_audit",
    "rank-posts": "creative_research.stages.rank_posts",
    "extract-references": "creative_research.stages.extract_references",
    "query": "creative_research.stages.query",
    "group-references": "creative_research.stages.group_references",
    "references": "creative_research.stages.references",
}


def print_help() -> None:
    print(
        f"""Creative Research CLI v{__version__}

Usage:
  creative-research <command> [options]

Canonical evidence pipeline:
  scrape             Apify TikTok profile scrape
  select-accounts    Merge scrape runs and keep selected accounts
  prepare-media      Archive TikTok covers/slides/avatars locally
  manifest-slides    Build manifest for all slideshow posts
  vision-slides      Gemini Vision analysis for slideshow posts (schema v2)
  download-videos    Download all non-slideshow TikTok videos + manifest
  vision-videos      Gemini analysis for full videos
  build-master       Merge slideshow + video Vision datasets
  build-warehouse    Backfill operator-aware canonical tables from creative_master
  analyze-performance Build account/operator relative performance baselines
  analyze-cadence     Build account/operator historical posting cadence
  build-families      Group repeated creative concepts with auditable similarity evidence
  calibrate-families  Measure family similarity/threshold behavior without changing families
  preview-families-v2 Preview conservative language-aware family clustering v2
  judge-family-candidates AI-judge ambiguous family pairs with cache/budget guards
  analyze-propagation Track family movement across verified operator accounts
  analyze-timeline    Build historical strategy windows + change points
  discover-patterns   Discover deterministic evidence-backed recurring patterns
  infer-strategies    Promote patterns into reviewable strategy hypotheses
  promote-knowledge   Build strategies/rules/lessons/templates/playbooks bank
  review-knowledge    Build/apply a prioritized human review queue
  build-intelligence-workspace Build static operator intelligence workspace
  intelligence       Serve the generated Operator Intelligence Lab
  lab                Friendly alias for the Operator Intelligence Lab
  intelligence-build Build/reuse the full deterministic intelligence pipeline
  quality-audit      Audit coverage, freshness, integrity, lineage, and trust status
  rank-posts         Rank master posts for reference selection
  extract-references Build whole-system map + representative reference workspace
  query              Filter normalized creative tables without ad-hoc Pandas
  group-references   Build descriptive candidate groups from a reference pack
  references         Serve a generated system/reference workspace locally

Project utilities:
  init               Create canonical workspace directories
  doctor             Check environment, binaries, and Python dependencies
  status             Summarize known pipeline outputs
  validate           Validate creative_master schema and invariants
  adopt              Link/copy existing completed outputs into canonical paths
  version            Print version
  help               Show this message

Examples:
  uv run creative-research init
  uv run creative-research status
  uv run creative-research validate
  uv run creative-research scrape config/target_accounts.example.txt --out data/00_raw/apify/run-001
  uv run creative-research prepare-media data/01_selected/targets --out data/02_media/tiktok
  uv run creative-research vision-slides data/03_manifests/slides/full_manifest.csv --out data/04_vision/slides
  uv run creative-research build-master --slides data/04_vision/slides/creative_study_v2.parquet --videos data/04_vision/videos/creative_video_study.parquet
  uv run creative-research build-warehouse --operators config/operators.toml
  uv run creative-research analyze-performance
  uv run creative-research analyze-cadence --timezone UTC
  uv run creative-research build-families
  uv run creative-research calibrate-families
  uv run creative-research preview-families-v2
  uv run creative-research judge-family-candidates --dry-run
  uv run creative-research analyze-propagation
  uv run creative-research analyze-timeline --timezone UTC
  uv run creative-research discover-patterns
  uv run creative-research infer-strategies
  uv run creative-research promote-knowledge
  uv run creative-research review-knowledge queue
  uv run creative-research build-intelligence-workspace
  uv run creative-research lab --open
  uv run creative-research intelligence-build --operators config/operators.toml
  uv run creative-research quality-audit
  uv run creative-research rank-posts data/05_master/creative_master.parquet --content-type slideshow --top 50
  uv run creative-research extract-references data/05_master/creative_master.parquet --out data/07_exports/study-reference-pack --top 30 --strategy system --media remote
  uv run creative-research references --dir data/07_exports/study-reference-pack --open

Detailed stage help:
  uv run creative-research vision-slides --help
  uv run creative-research vision-videos --help
  uv run creative-research build-warehouse --help
  uv run creative-research analyze-performance --help
  uv run creative-research analyze-cadence --help
  uv run creative-research build-families --help
  uv run creative-research calibrate-families --help
  uv run creative-research preview-families-v2 --help
  uv run creative-research judge-family-candidates --help
  uv run creative-research analyze-propagation --help
  uv run creative-research analyze-timeline --help
  uv run creative-research discover-patterns --help
  uv run creative-research infer-strategies --help
  uv run creative-research promote-knowledge --help
  uv run creative-research review-knowledge --help
  uv run creative-research build-intelligence-workspace --help
  uv run creative-research intelligence --help
  uv run creative-research lab --help
  uv run creative-research intelligence-build --help
  uv run creative-research quality-audit --help
  uv run creative-research extract-references --help
  uv run creative-research references --help
"""
    )


def cmd_init() -> int:
    root = project_root()
    for rel in WORKSPACE_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    print(f"Workspace initialized: {root}")
    for rel in WORKSPACE_DIRS:
        print(f"  {rel}")
    return 0


def _check_import(name: str) -> tuple[bool, str]:
    try:
        spec = importlib.util.find_spec(name)
        return (spec is not None, "ok" if spec is not None else "missing")
    except Exception as exc:
        return False, f"error: {exc}"


def doctor_checks() -> list[tuple[str, bool, str, bool]]:
    """Return checks as (name, ok, detail, required)."""
    checks: list[tuple[str, bool, str, bool]] = []

    uv = shutil.which("uv")
    checks.append(("uv", bool(uv), uv or "not found", True))

    ffprobe = shutil.which("ffprobe")
    checks.append(("ffprobe", bool(ffprobe), ffprobe or "not found", False))

    ytdlp_bin = shutil.which("yt-dlp")
    ytdlp_mod, _ = _check_import("yt_dlp")
    checks.append(
        (
            "yt-dlp",
            bool(ytdlp_bin or ytdlp_mod),
            ytdlp_bin or ("python module" if ytdlp_mod else "not found"),
            True,
        )
    )

    for mod in ["apify_client", "httpx", "pandas", "pyarrow", "google.genai", "pydantic"]:
        ok, detail = _check_import(mod)
        checks.append((f"python:{mod}", ok, detail, True))

    for env_name in ["APIFY_TOKEN", "GEMINI_API_KEY"]:
        present = bool(os.environ.get(env_name))
        checks.append((f"env:{env_name}", present, "set" if present else "not set", False))

    return checks


def cmd_doctor() -> int:
    checks = doctor_checks()
    width = max(len(name) for name, _, _, _ in checks)
    hard_fail = False
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


def _replace_destination(dest: Path, replace: bool) -> None:
    if not dest.exists() and not dest.is_symlink():
        return
    if not replace:
        raise SystemExit(
            f"Destination already exists: {dest}\n"
            "Use --replace only if you intentionally want to replace it."
        )
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)


def _adopt_one(src: str | None, dest: Path, mode: str, replace: bool) -> None:
    if not src:
        return
    source = Path(src).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Source does not exist: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _replace_destination(dest, replace)
    if mode == "symlink":
        dest.symlink_to(source, target_is_directory=source.is_dir())
    elif mode == "copy":
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
    else:
        raise SystemExit(f"Unsupported adopt mode: {mode}")
    print(f"{mode}: {dest} -> {source}")


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
    _adopt_one(ns.selected, root / "data/01_selected/targets", ns.mode, ns.replace)
    _adopt_one(ns.media, root / "data/02_media/tiktok", ns.mode, ns.replace)
    _adopt_one(ns.slides_manifest, root / "data/03_manifests/slides", ns.mode, ns.replace)
    _adopt_one(ns.video_media, root / "data/03_video_media", ns.mode, ns.replace)
    _adopt_one(ns.slides_vision, root / "data/04_vision/slides", ns.mode, ns.replace)
    _adopt_one(ns.video_vision, root / "data/04_vision/videos", ns.mode, ns.replace)
    _adopt_one(ns.master, root / "data/05_master", ns.mode, ns.replace)

    for item in ns.apify:
        if "=" not in item:
            raise SystemExit("--apify expects NAME=PATH")
        name, src = item.split("=", 1)
        name = name.strip()
        if not name or "/" in name or "\\" in name:
            raise SystemExit(f"Invalid Apify run name: {name!r}")
        _adopt_one(src, root / "data/00_raw/apify" / name, ns.mode, ns.replace)

    return cmd_status([])


def _count_lines(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return None


def _count_media_posts(root: Path) -> int | None:
    if not root.exists():
        return None
    total = 0
    for account in root.iterdir():
        if not account.is_dir():
            continue
        for post in account.iterdir():
            if (
                post.is_dir()
                and post.name != "profile"
                and ((post / "meta.json").exists() or (post / "raw.json").exists())
            ):
                total += 1
    return total


def status_rows(root: Path) -> list[dict[str, object]]:
    candidates = [
        (
            "selected normalized posts",
            root / "data/01_selected/targets/normalized/posts.jsonl",
            "lines",
        ),
        ("local media posts", root / "data/02_media/tiktok", "media"),
        ("slideshow manifest", root / "data/03_manifests/slides/full_manifest.jsonl", "lines"),
        ("video manifest", root / "data/03_video_media/video_manifest.jsonl", "lines"),
        (
            "slideshow vision results",
            root / "data/04_vision/slides/creative_study_v2.jsonl",
            "lines",
        ),
        (
            "video vision results",
            root / "data/04_vision/videos/creative_video_study.jsonl",
            "lines",
        ),
        ("creative master", root / "data/05_master/creative_master.jsonl", "lines"),
        ("post performance", root / "data/06_analytics/post_performance.parquet", "file"),
        ("posting cadence", root / "data/06_analytics/posting_cadence.parquet", "file"),
        ("creative families", root / "data/06_analytics/creative_families.parquet", "file"),
        ("cross-account propagation", root / "data/06_analytics/cross_account_propagation.parquet", "file"),
        ("account role evidence", root / "data/06_analytics/account_role_evidence.parquet", "file"),
        ("strategy timeline", root / "data/06_analytics/strategy_windows.parquet", "file"),
        ("evidence patterns", root / "data/06_analytics/patterns.parquet", "file"),
        ("strategy hypotheses", root / "data/06_analytics/strategy_hypotheses.parquet", "file"),
        ("knowledge catalog", root / "data/07_knowledge/knowledge_catalog.parquet", "file"),
        ("intelligence workspace", root / "data/07_exports/operator-intelligence/workspace.json", "file"),
        ("intelligence quality", root / "data/07_exports/operator-intelligence/quality_report.json", "file"),
    ]
    rows: list[dict[str, object]] = []
    for label, path, kind in candidates:
        if kind == "lines":
            count = _count_lines(path)
        elif kind == "media":
            count = _count_media_posts(path)
        else:
            count = 1 if path.is_file() else None
        rows.append(
            {
                "label": label,
                "path": str(path.relative_to(root)),
                "present": count is not None,
                "count": count,
            }
        )
    return rows


def cmd_status(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="creative-research status")
    parser.add_argument("--json", action="store_true", dest="as_json")
    ns = parser.parse_args(args)

    root = project_root()
    rows = status_rows(root)
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

    from creative_research.validation import read_table, validate_master

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


def dispatch_stage(command: str, args: list[str]) -> int:
    module = COMMANDS[command]
    old_argv = sys.argv[:]
    try:
        sys.argv = [command, *args]
        runpy.run_module(module, run_name="__main__")
        return 0
    finally:
        sys.argv = old_argv


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"help", "--help", "-h"}:
        print_help()
        raise SystemExit(0)

    command, rest = args[0], args[1:]
    if command in COMMANDS:
        raise SystemExit(dispatch_stage(command, rest))
    if command == "init":
        raise SystemExit(cmd_init())
    if command == "doctor":
        raise SystemExit(cmd_doctor())
    if command == "status":
        raise SystemExit(cmd_status(rest))
    if command == "validate":
        raise SystemExit(cmd_validate(rest))
    if command == "adopt":
        raise SystemExit(cmd_adopt(rest))
    if command in {"version", "--version", "-V"}:
        print(__version__)
        raise SystemExit(0)

    print(f"Unknown command: {command}\n", file=sys.stderr)
    print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
