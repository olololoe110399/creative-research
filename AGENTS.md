# Repository Guidelines

## Scope and structure

This repository only captures public TikTok records, downloads files and exports
portable datasets. Do not add AI interpretation, analytics, production workflows,
operator/team state or browser UI. Read docs/architecture.md and docs/dataset-contract.md.
Package: src/creative_research/. Acquisition/archive/export belong in capture/;
shared I/O in infrastructure/; argument parsing in cli/commands/. Tests mirror features.
Dataset contracts live in capture/contracts.py; commands in cli/registry.py.

## Development

uv sync --locked --all-groups installs pinned dependencies. make check runs lint,
formatting, mypy, pytest/coverage and docs verification. make build verifies exact
release contents; make release-check tests fresh installs. Target capture regressions
with uv run python -m pytest tests/capture -q. doctor --json checks dependencies.

## Code and tests

Use four spaces, type hints, future annotations, snake_case and Ruff's 100-character
line length/Python 3.11 target. CLI parses/presents; workflows own behavior. Business
modules must not import CLI/argparse. Resolve paths with resolve_path, confine imported
identifiers and use shared atomic writers. Environment loading is explicit; imports
have no requests/writes. Tests use tmp_path/monkeypatch and mock Apify, HTTP and yt-dlp.
Cover invalid inputs, failure/retry, interruption, lineage and dataset integrity.
Branch coverage must remain at least 70%; fixtures are not live-provider proof.

## Data and delivery

Never commit keys, private config, datasets or media. Preserve existing raw evidence,
archives and private state; run one writer per project. Safe templates use *.example.*.
Commits use imperative or scoped Conventional subjects. PRs explain behavior, list
validation and call out compatibility/schema/lineage effects and verification gaps.
