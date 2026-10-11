"""CLI adapter for downloading covers, avatars, slides and videos."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys

from creative_research.capture.download import DownloadOptions, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, help="Crawl/selected folder containing posts/*.jsonl"
    )
    parser.add_argument("--out", default="data/media")
    parser.add_argument("--accounts", nargs="+", help="Optional account subset")
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    for kind in ("slides", "covers", "avatars", "videos"):
        parser.add_argument(f"--no-{kind}", action="store_true")
    parser.add_argument("--cookies-from-browser")
    parser.add_argument("--cookies-file")
    parser.add_argument("--dry-run", action="store_true", help="Plan without writes or network")
    parser.add_argument(
        "--json", action="store_true", help="Print one JSON report; progress uses stderr"
    )
    return parser


def main() -> None:
    args = vars(build_parser().parse_args())
    machine = args.pop("json")
    with contextlib.redirect_stdout(sys.stderr) if machine else contextlib.nullcontext():
        result = run(DownloadOptions(**args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failed"]:
        raise SystemExit(1)
