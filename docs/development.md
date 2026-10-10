# Development

## Quality gates

```sh
uv sync --locked --all-groups
make lint                 # Ruff correctness, imports, naming and bug-prone patterns
make format-check         # Formatting without writes
make format               # Format owned Python source/tests/scripts
make typecheck            # mypy; annotations required for every package function
make test                 # pytest and branch coverage, minimum 70%
make ui-check             # Six JS syntax checks and two Node smokes
make docs-check           # Generated catalog, links and documented commands
make skill-check          # Agent Skills specification validation
make check                # All checks above
make build                # Wheel/sdist and exact package-content verification
make release-check        # Fresh installs and offline end-to-end commands
make snapshot             # Allowlisted public ZIP without Git history/local data
```

During iteration use a targeted regression, such as
`uv run python -m pytest tests/pipeline/test_intelligence_pipeline.py -q`.
Quality tools target owned `src/`, `tests/`, `scripts/` and `skills/`, not local user utilities.
Portable bridge scripts and installer have a separate mypy check. Skill contract
tests live in `tests/skills/`; see [Agent Skills](agent-skills.md) for independent
forward-use/host checks and the distinction between fixtures and AI accuracy.

## Testing boundaries

Unit tests cover deterministic transformations and config/logging/path/storage.
Integration tests cover real stage entrypoints, loopback HTTP, durable state imports
and synthetic full builds followed by reuse. Failure tests cover interruption,
publication rollback, unsafe paths, invalid bodies and retired endpoints.
Providers are mocked: tests must not require keys, external data or paid calls.
Tests are grouped by owning feature (`analysis/`, `capture/`, `vision/`, `pipeline/`,
etc.), with package/release contracts in `tests/architecture/`. A feature suite may
contain both pure unit cases and isolated filesystem/CLI integration cases.
Pytest's importlib mode avoids adding test directories to Python's import search path.

Coverage includes all package modules, including mocked Vision workflows. Regression
tests freeze pre-refactor response fields/enums/defaults and verify resource cleanup,
retry classification, import side effects, cycle-free dependencies and path confinement.
Architecture regressions also prevent non-CLI code from importing argument parsers
and exercise a full build without loading the CLI or mutating process arguments.
Aggregate coverage is not proof of live provider behavior. Third-party modules without
type stubs remain untyped; strengthen narrow boundaries instead of suppressing errors globally.
Node smokes are not interactive browser, accessibility or CSS verification.

## Stable interfaces and releases

The CLI, canonical evidence schemas and generated exports are supported interfaces.
Python modules are internal implementation details. Keep schema identifiers stable
when their meaning has not changed. There is no database to initialize or migrate.
Preserve durable team-state/rights imports when changing filesystem contracts.

CI uses locked installs, Python 3.11/3.13, Linux/macOS, the complete gate, package
verification and fresh wheel/sdist installs. It is read-only and never publishes.
For release preparation run `make check release-check snapshot` from a clean checkout.
Review the snapshot, configure private security reporting and authorize publication
separately. Future release notes summarize actual user-facing changes.

Live capture/Vision staging QA, representative-corpus benchmarks and interactive UI
QA require separate evidence. Public deployment, distributed writes and unbounded
corpora are not supported. Do not describe a green offline gate as certification.
