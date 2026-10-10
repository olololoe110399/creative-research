"""CLI adapter for the local workspace server."""

from __future__ import annotations

import argparse

from creative_research.workspaces.server import serve_references


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a generated Reference Workspace.")
    parser.add_argument("--dir", default="data/07_exports/reference-pack")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    serve_references(
        directory=args.dir, host=args.host, port=args.port, open_browser=args.open_browser
    )


if __name__ == "__main__":
    main()
