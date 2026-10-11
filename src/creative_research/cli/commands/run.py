"""CLI adapter for the durable capture/download/export pipeline."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys

from creative_research.capture.pipeline import PipelineOptions, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts-file", help="Required for a new run; saved accounts on resume")
    parser.add_argument(
        "--out", required=True, help="Run directory containing raw/media/datasets/checkpoints"
    )
    parser.add_argument("--resume", action="store_true", help="Continue with saved configuration")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Publish inventoried gaps; exit remains nonzero",
    )
    parser.add_argument(
        "--recover-run", dest="recover_runs", action="append", metavar="BATCH=RUN_ID"
    )
    for name in ("batch-size", "max-posts", "actor-timeout", "concurrency", "retries"):
        parser.add_argument(f"--{name}", type=int)
    for name in ("max-charge-usd", "timeout"):
        parser.add_argument(f"--{name}", type=float)
    parser.add_argument("--oldest-date")
    parser.add_argument("--newest-date")
    parser.add_argument("--cookies-from-browser")
    parser.add_argument("--cookies-file")
    parser.add_argument("--zip", dest="include_zip", action="store_true", default=None)
    parser.add_argument(
        "--json", action="store_true", help="One final JSON report; progress on stderr"
    )
    return parser


def main() -> None:
    args = vars(build_parser().parse_args())
    machine = args.pop("json")
    with contextlib.redirect_stdout(sys.stderr):
        result = run(PipelineOptions(**args))
    if machine:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Pipeline {result['status']}: {result.get('dataset') or args['out']}")
        if result.get("error"):
            print(result["error"], file=sys.stderr)
    if result["status"] != "completed":
        raise SystemExit(130 if result["status"] == "interrupted" else 1)
