#!/usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import http.server
import webbrowser
from pathlib import Path

from creative_research.intelligence_workspace import validate_intelligence_workspace
from creative_research.pathing import project_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve a generated Operator Intelligence Workspace."
    )
    parser.add_argument("--dir", default="data/07_exports/operator-intelligence")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def resolve_intelligence_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return path.resolve()


def main() -> None:
    args = build_parser().parse_args()
    root = resolve_intelligence_dir(args.dir)
    missing = validate_intelligence_workspace(root)
    if missing:
        rendered = "\n".join(f"  - {name}" for name in missing)
        raise SystemExit(
            f"Operator Intelligence Workspace is not ready: {root}\n"
            f"Missing required files:\n{rendered}\n\n"
            "Build it first with creative-research build-intelligence-workspace."
        )

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(root),
    )
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    actual_port = int(server.server_address[1])
    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{browser_host}:{actual_port}/"
    print(f"Intelligence workspace: {root}")
    print(f"Serving:                {url}")
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
