"""CLI adapter for the local Operator Intelligence Lab."""

from __future__ import annotations

import argparse

from creative_research.workspaces.server import serve_lab


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local Operator Intelligence Lab.")
    parser.add_argument("--dir", default="data/07_exports/operator-intelligence")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable creator-team state changes.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    serve_lab(
        directory=args.dir,
        host=args.host,
        port=args.port,
        open_browser=args.open_browser,
        read_only=args.read_only,
    )


if __name__ == "__main__":
    main()
