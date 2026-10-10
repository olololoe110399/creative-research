# Repository Guidelines

## Project Structure & Module Organization

The package lives in `src/creative_research/`. Put calculations in `analysis/`, shared I/O in `infrastructure/`, and parsing in `cli/commands/`. Group features in `capture/`, `vision/`, `production/`, `references/` and `operating/`. `pipeline/steps/` publishes offline outputs; `workspaces/` owns browser exports, HTTP and assets. `skills/creative-research/` is the canonical portable skill, not a second engine; installation copies are generated. Tests mirror features: `tests/<feature>/test_<subject>.py`. Read `docs/architecture.md` and `docs/agent-skills.md`. Safe config templates use `*.example.*`; `data/` is local evidence.

## Build, Test, and Development Commands

- `uv sync --locked --all-groups` installs pinned runtime/development dependencies.
- `make check` runs lint, formatting, mypy, coverage, UI smokes, docs and skill validation.
- `make format` formats code; `make build` verifies distributions; `make release-check` tests fresh installs.
- `uv run python -m pytest tests/pipeline/ -q` runs targeted regressions.
- `uv run creative-research doctor --json` checks dependencies.
- `uv run creative-research demo --out ./demo-workspace` exercises all offline stages with synthetic evidence.

Inspect UI with `uv run creative-research --root ./demo-workspace lab --read-only --open`. Servers are loopback-only and unauthenticated.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, and `from __future__ import annotations`. Ruff targets Python 3.11 with 100-character lines. Modules, functions and variables use `snake_case`; classes use `PascalCase`; constants use `UPPER_SNAKE_CASE`. Keep commands thin and logic focused. Preserve JavaScript/CSS style; avoid framework dependencies.

Declare contracts in `pipeline/contracts.py` and commands in `cli/registry.py`. Business modules must not import CLI/`argparse`; workflows call analysis and shared I/O. Resolve paths with `resolve_path`; use shared atomic writers. Load environment files only explicitly. Keep imports free of network calls and writes.

## Testing Guidelines

Use pytest functions named `test_<behavior>` and isolated `tmp_path`/`monkeypatch` fixtures. Mock Apify, TikTok and Gemini; tests must not make paid/external requests. Cover invalid input, rollback, interrupted publication, schema/lineage changes and durable data imports. Branch coverage must remain at least 70%, including mocked Vision stages; fixture coverage is not proof of live provider behavior.

## Commit & Pull Request Guidelines

Use imperative subjects (`Preserve asset attestations`) or scoped Conventional Commits (`style(ui): ...`). Keep commits focused. PRs explain changes, list validation commands, link issues, and include screenshots for UI changes. Call out schema, migration, rights and evidence-lineage effects.

## Security & Data Handling

Never commit keys, private config, datasets or media. Preserve raw evidence and private operating state. Run one writer per project. Do not claim production readiness from fixture tests alone; disclose live-provider, browser, concurrency and performance verification gaps.
