"""CLI adapter for building the Lab export."""

from __future__ import annotations

import argparse

from creative_research.pipeline.contracts import DEFAULT_WORKSPACE, WORKSPACE_INPUTS
from creative_research.pipeline.steps import build_intelligence_workspace as workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a static Operator Intelligence Workspace from existing warehouse, "
            "analytics, strategy, and knowledge outputs. No expensive stage is rerun."
        )
    )
    for name, default in WORKSPACE_INPUTS.items():
        parser.add_argument(
            "--" + name.replace("_", "-"),
            default=default,
        )
    parser.add_argument(
        "--out",
        default=DEFAULT_WORKSPACE,
    )
    parser.add_argument(
        "--raw-root",
        default=None,
        help="Optional public TikTok scrape archive for recovering real music/caption/hashtag metadata; auto-detects data/00_raw/apify.",
    )
    return parser


def main() -> None:
    workflow.run(**vars(build_parser().parse_args()))


if __name__ == "__main__":
    main()
