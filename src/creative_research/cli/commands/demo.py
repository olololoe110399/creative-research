"""Offline, synthetic onboarding; never adopt or overwrite a real workspace."""

from __future__ import annotations

import argparse

from creative_research.cli.commands.intelligence_build import main as build
from creative_research.infrastructure.paths import resolve_path
from creative_research.infrastructure.storage import write_json
from creative_research.pipeline.demo_data import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the complete offline pipeline with eight synthetic posts. No keys or network required."
    )
    parser.add_argument(
        "--out",
        required=True,
        help="New or empty demo project directory; existing evidence is never overwritten.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the pipeline JSON report; progress goes to stderr.",
    )
    args = parser.parse_args()
    root = resolve_path(args.out)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        parser.error("Demo output must be a new or empty directory. Choose another --out path.")
    root.mkdir(parents=True, exist_ok=True)
    write_json(
        root / "SYNTHETIC_DEMO.json",
        {
            "synthetic": True,
            "scope": "Fake onboarding data, not operator research or licensed production assets.",
        },
    )
    seed_demo(root)
    build(["--root", str(root)] + (["--json"] if args.json else []))


if __name__ == "__main__":
    main()
