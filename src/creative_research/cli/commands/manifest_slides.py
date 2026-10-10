"""Command-line adapter for manifest slides workflow."""

from __future__ import annotations

import argparse

import creative_research.capture.manifests as service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="data/02_media/tiktok directory")
    parser.add_argument("--out", default="data/03_manifests/slides")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service.run(input_dir=args.input, out=args.out)


if __name__ == "__main__":
    main()
