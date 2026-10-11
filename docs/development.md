# Development

```sh
make help
uv sync --locked --all-groups
make check
make build
make release-check
make snapshot
```

Bare `make` shows help without installing dependencies or running acquisition.
Use `make sync` to install all locked groups. Makefile commands accept `UV` for an
alternate uv executable; every `uv run` uses --locked and fails on lockfile drift.
Pipeline acquisition/resume options are documented in the
[capture workflow](capture-workflow.md).

make check runs Ruff lint/format, mypy, pytest with a 70% coverage floor and branch
tracking enabled, and CLI documentation verification. Tests mock Apify, HTTP and
yt-dlp: no external calls or real media. Integration tests cover
capture/download/export, relocation, missing
assets, retries, interrupted publication and integrity verification. Pipeline tests
cover paid-run reuse, uncertain launch reconciliation, immutable partial revisions,
source/cache tampering, ZIP recovery and rejection of concurrent writers.

Build verifies exact source/wheel contents and excludes local data, config, secrets
and removed research modules. Release checks install wheel and sdist into fresh
environments and exercise all help, offline export, relocated validation and a
mocked complete pipeline with resume that performs no duplicate provider requests.
CI tests Python 3.11/3.13 on Linux/macOS. Live provider quality and large-corpus
performance require independent verification. Run one writer per project.

For documentation changes, run `make docs-check` and `git diff --check`. Catalog
text comes from cli/registry.py; regenerate it with
`uv run python scripts/generate_cli_docs.py` when commands change. Usage and
consumer guides stay concise; contracts document field semantics and recovery
behavior. Verify statements about defaults, exit codes and filesystem writes
against the command adapters and capture services.
