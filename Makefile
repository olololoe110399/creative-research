UV ?= uv
.DEFAULT_GOAL := help

.PHONY: help sync lint format format-check typecheck test docs-check check build \
        release-check snapshot doctor

help:
	@printf '%s\n' \
		'Capture/download/export development commands:' \
		'  sync           Install locked runtime and development dependencies' \
		'  lint           Check Python lint rules' \
		'  format         Format Python sources, tests and scripts' \
		'  format-check   Check Python formatting without changes' \
		'  typecheck      Check package types' \
		'  test           Run offline tests with coverage' \
		'  docs-check     Check CLI catalog, local links and example syntax' \
		'  check          Run lint, format, types, tests and docs checks' \
		'  build          Build and verify wheel/source distributions' \
		'  release-check  Verify fresh installs and mocked pipeline/resume' \
		'  snapshot       Build a public source ZIP without local data' \
		'  doctor         Check capture/download dependencies' \
		'Use creative-research run --help for acquisition and resume options.'

sync:
	$(UV) sync --locked --all-groups

lint:
	$(UV) run --locked ruff check src tests scripts

format:
	$(UV) run --locked ruff format src tests scripts

format-check:
	$(UV) run --locked ruff format --check src tests scripts

typecheck:
	$(UV) run --locked mypy

test:
	$(UV) run --locked python -m pytest --cov=creative_research --cov-report=term-missing --cov-fail-under=70

docs-check:
	$(UV) run --locked python scripts/generate_cli_docs.py --check

check: lint format-check typecheck test docs-check

build:
	$(UV) build
	$(UV) run --locked python scripts/verify_distribution.py

release-check: build
	$(UV) run --locked python scripts/verify_installation.py

snapshot: build
	$(UV) run --locked python scripts/prepare_public_snapshot.py

doctor:
	$(UV) run --locked creative-research doctor
