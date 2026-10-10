# Contributing

## Setup and workflow

Use Python 3.11+ and `uv sync --locked --all-groups`. Run `make check` before sending
a change. `make build` verifies distributions. See [development](docs/development.md)
for the individual commands; no provider account is required for tests or the demo.

Inspect `git status` before editing. Preserve unrelated changes and real evidence.
Use a focused branch (`codex/<topic>` for agent-created branches). Reproduce a bug
with a failing regression test, implement the smallest appropriate boundary change,
and run the relevant tests followed by the full gate.

## Code standards

Use four spaces, Python type annotations and a 100-character Ruff line length.
Names are `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
Use Ruff for imports, formatting, naming and bug-prone patterns; mypy checks the full
package and requires annotations for every function. Third-party modules without
stubs remain untyped; this is not strict typing of every dataframe cell.

Keep calculations in `analysis/` or the owning feature package. Place reusable
offline publication in `pipeline/steps/`; `cli/commands/` only parses arguments and
adapts results/errors. No business module may import CLI code or `argparse`.
Resolve user paths with `resolve_path`, validate imported identifiers with
`confined_path`, and publish tables/reports through shared atomic writers.
Declare workspace contracts once in `pipeline/contracts.py`; commands in `cli/registry.py`.

Never add import-time configuration loading, network calls or filesystem writes.
Use application loggers with context fields, not credentials or complete evidence
payloads. Raise clear errors that identify the failing operation and safe next step.
Avoid abstractions that do not remove real duplication or isolate a testable boundary.

## Tests and UI

Use `tests/<feature>/test_<subject>.py` and `test_<behavior>` functions, isolated `tmp_path`
fixtures and mocked providers. Tests must not spend money or depend on external
network state. Cover invalid input, retries/failure, unchanged-output behavior and
data preservation when changing contracts. The offline integration test exercises
all twelve stages and a subsequent reuse run.

Keep vanilla workspace assets framework-free. Run both Node smoke tests and syntax
checks; include screenshots and browser QA notes for visible UI changes. Automated
smokes do not replace accessibility or interactive browser verification.

## Commits and pull requests

Use imperative subjects or scoped Conventional Commits, for example
`Preserve asset attestations` or `fix(cli): retain failed-stage diagnostics`.
Keep commits focused; do not mix generated datasets with source changes.

A PR should explain purpose and behavior changes, link relevant issues, list exact
validation commands/results, and disclose unverified runtime behavior. Call out
schema/migration effects, retained backups, evidence lineage, rights handling and
intentional compatibility changes. Update docs; maintainers summarize user-facing
changes in release notes for future versions, without inventing pre-release history.
Do not include secrets or private research in logs, screenshots or attachments.
