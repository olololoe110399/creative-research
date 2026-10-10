# Repository Guidelines

## Project Structure & Module Organization

The package lives in `src/creative_research/`. Put calculations in `analysis/`, shared I/O in `infrastructure/`, and argument parsing in `cli/commands/`. Group features in `capture/`, `vision/`, `production/`, `references/` and `operating/`. `pipeline/steps/` publishes offline outputs; `workspaces/` owns browser exports, HTTP and `assets/`. Root holds bootstrap/shared primitives. Tests mirror features: `tests/<feature>/test_<subject>.py`. Read `docs/architecture.md`; `config/*.example.*` contains safe templates. `data/` is local evidence.

## Build, Test, and Development Commands

- `uv sync --locked --all-groups` installs pinned runtime/development dependencies.
- `make check` runs lint, format checking, mypy, coverage, UI smokes and generated-doc checks.
- `make format` formats code; `make build` verifies distributions; `make release-check` tests fresh installs.
- `uv run python -m pytest tests/pipeline/ -q` runs targeted regressions.
- `uv run creative-research doctor --json` checks dependencies.
- `uv run creative-research demo --out ./demo-workspace` exercises all offline stages with synthetic evidence.

Inspect UI with `uv run creative-research --root ./demo-workspace lab --read-only --open`. Servers are loopback-only and unauthenticated.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, and `from __future__ import annotations`. Ruff targets Python 3.11 with a 100-character line length. Name modules, functions, and variables in `snake_case`; classes in `PascalCase`; constants in `UPPER_SNAKE_CASE`. Keep commands thin; place reusable logic in focused modules. Preserve JavaScript/CSS style and avoid framework dependencies.

Declare contracts in `pipeline/contracts.py` and commands in `cli/registry.py`. Business modules must not import CLI/`argparse`; workflows call analysis and shared I/O. Resolve paths with `resolve_path`; use shared atomic writers. Load environment files only explicitly. Keep imports free of network calls and writes.

## Testing Guidelines

Use pytest functions named `test_<behavior>` and isolated `tmp_path`/`monkeypatch` fixtures. Mock Apify, TikTok and Gemini; tests must not make paid/external requests. Cover invalid input, rollback, interrupted publication, schema/lineage changes and durable data imports. Branch coverage must remain at least 70%, including mocked Vision stages; fixture coverage is not proof of live provider behavior.

## Commit & Pull Request Guidelines

Use imperative subjects (`Preserve asset attestations`) or scoped Conventional Commits (`style(ui): ...`). Keep commits focused. PRs explain changes, list validation commands, link issues, and include screenshots for UI changes. Call out schema, migration, rights and evidence-lineage effects.

## Security & Data Handling

Never commit keys, private config, datasets or media. Preserve raw evidence and private operating state. Run one writer per project. Do not claim production readiness from fixture tests alone; disclose live-provider, browser, concurrency and performance verification gaps.
