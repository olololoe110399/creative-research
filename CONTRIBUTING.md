# Contributing

Use Python 3.11+, uv sync --locked --all-groups, make check and make release-check.
Inspect git status and preserve unrelated changes/local data. Agent branches use
codex/<topic>. See [architecture](docs/architecture.md) and [development](docs/development.md).

Keep scope to public records, media downloads and portable datasets. CLI adapters
parse/present; capture workflows own behavior. No business imports of CLI/argparse;
no import-time writes/requests. Use type annotations, Ruff, path confinement and
shared atomic writers. Dataset contracts live in capture/contracts.py.

Use isolated pytest fixtures and mock providers. Cover invalid input, retries,
partial failure, interrupted publication, unchanged sources and export portability.
Never spend money or depend on external services in tests. Keep coverage at least 70%.

Commits use imperative or scoped Conventional subjects. PRs explain the problem and
behavior, list validation, and disclose breaking contracts and live-provider gaps.
Never include credentials, datasets or media in changes or logs.
