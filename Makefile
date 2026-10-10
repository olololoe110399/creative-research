UV ?= uv

.PHONY: sync lint format format-check typecheck test ui-check docs-check check build release-check snapshot doctor

sync:
	$(UV) sync --locked --all-groups

lint:
	$(UV) run ruff check src tests scripts

format:
	$(UV) run ruff format src tests scripts

format-check:
	$(UV) run ruff format --check src tests scripts

typecheck:
	$(UV) run mypy

test:
	$(UV) run python -m pytest --cov=creative_research --cov-report=term-missing --cov-fail-under=70

ui-check:
	node --check src/creative_research/workspaces/assets/references/app.js
	node --check src/creative_research/workspaces/assets/lab/app.js
	node --check src/creative_research/workspaces/assets/lab/product_ui.js
	node --check src/creative_research/workspaces/assets/lab/research_ui.js
	node --check src/creative_research/workspaces/assets/lab/operating_ui.js
	node --check src/creative_research/workspaces/assets/lab/production_ui.js
	node tests/workspaces/ui_research_smoke.cjs
	node tests/workspaces/ui_security_smoke.cjs

docs-check:
	$(UV) run python scripts/generate_cli_docs.py --check

check: lint format-check typecheck test ui-check docs-check

build:
	$(UV) build
	$(UV) run python scripts/verify_distribution.py

release-check: build
	$(UV) run python scripts/verify_installation.py

snapshot: build
	$(UV) run python scripts/prepare_public_snapshot.py

doctor:
	$(UV) run creative-research doctor
