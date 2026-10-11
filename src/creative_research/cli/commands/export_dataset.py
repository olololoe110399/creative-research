"""Command-line adapter for the offline dataset handoff."""

from __future__ import annotations

import argparse
import json

from creative_research.capture.export_dataset import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export selected crawl records and local media.")
    parser.add_argument("--input", dest="input_dir", required=True)
    parser.add_argument("--media-root", default="data/media")
    parser.add_argument("--out", required=True, help="New output directory; never overwritten.")
    parser.add_argument(
        "--zip", dest="include_zip", action="store_true", help="Also write OUT.zip."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Inspect/hash sources without writes."
    )
    parser.add_argument("--json", action="store_true", help="Output is always JSON")
    parser.add_argument(
        "--require-verified-media",
        action="store_true",
        help="Only export files verified for this capture by download-media",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    values = vars(args)
    values.pop("json")
    print(json.dumps(run(**values), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
