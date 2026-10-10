# Command catalog

Generated from `cli/registry.py`; run `make docs-check` to detect drift.
Use `creative-research <command> --help` for options and required inputs.

## Capture & interpret

- `operator-setup`: Confirm operator/account grouping once, before scraping.
- `scrape`: Apify TikTok profile scrape (confirmed grouping required).
- `select-accounts`: Merge scrape runs and keep selected accounts.
- `prepare-media`: Archive TikTok covers/slides/avatars locally.
- `manifest-slides`: Build manifest for all slideshow posts.
- `vision-slides`: Gemini Vision analysis for slideshow posts (schema v2).
- `download-videos`: Download all non-slideshow TikTok videos + manifest.
- `vision-videos`: Gemini analysis for full videos.
- `build-master`: Merge slideshow + video Vision datasets.

## Analyze & infer

- `build-warehouse`: Backfill operator-aware canonical tables from creative_master.
- `analyze-performance`: Build account/operator relative performance baselines.
- `analyze-cadence`: Build account/operator historical posting cadence.
- `build-families`: Group repeated creative concepts with auditable similarity evidence.
- `calibrate-families`: Measure family similarity/threshold behavior without changing families.
- `preview-families-v2`: Inspect language-aware family clustering before publishing outputs.
- `judge-family-candidates`: AI-judge ambiguous family pairs with cache/budget guards.
- `analyze-propagation`: Track family movement across verified operator accounts.
- `analyze-timeline`: Build historical strategy windows + change points.
- `discover-patterns`: Discover deterministic evidence-backed recurring patterns.
- `infer-strategies`: Promote patterns into reviewable strategy hypotheses.
- `promote-knowledge`: Build strategies/rules/lessons/templates/playbooks bank.

## Build & inspect

- `intelligence-build`: Build/reuse the full deterministic intelligence pipeline.
- `build-intelligence-workspace`: Build static operator intelligence workspace.
- `production-kit`: Export content recipes, account blueprint, assets and team handoff ZIP.
- `review-knowledge`: Build/apply a prioritized human review queue.
- `quality-audit`: Audit coverage, freshness, integrity, lineage, and trust status.
- `outcome-audit`: Validate research brief, role flows, playbook and trust boundaries.
- `rank-posts`: Rank master posts for reference selection.
- `extract-references`: Build whole-system map + representative reference workspace.
- `query`: Filter normalized creative tables without ad-hoc Pandas.
- `group-references`: Build descriptive candidate groups from a reference pack.

## Local workspaces

- `lab`: Serve the generated Operator Intelligence Lab.
- `references`: Serve a generated system/reference workspace locally.

## Project utilities

- `init`: Create canonical workspace directories.
- `demo`: Build a synthetic offline example in a new directory.
- `doctor`: Check environment, binaries, and Python dependencies.
- `status`: Summarize known pipeline outputs.
- `validate`: Validate creative_master schema and invariants.
- `adopt`: Link/copy existing completed outputs into canonical paths.
