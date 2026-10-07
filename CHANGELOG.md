# Changelog

## 0.9.0 - 2026-10-07

- Upgrade the handoff contract to `creative-reference-pack-v3`.
- Give every post in the reference population a stable `POST-xxxxxx` item ID and lightweight normalized Vision detail.
- Keep `REF-xxxx` as Suggested examples only; users can now inspect and select any full-population post from a Structure group.
- Add `population.json` for UI browsing and `population.jsonl` for downstream Creative Bank import.
- Add actual thumbnails to full-population Group Detail and large media cards for Suggested examples.
- Add group search/account/language filters, sorting, per-row selection, Select suggested, Select visible, and Clear group selection.
- Add a persistent selection bar and Selected-page coverage audit for group/account/language concentration.
- Export `selected.json` using full-population POST IDs so selection is no longer limited to the suggested sample.


## 0.8.2 - 2026-10-07

- Add visual previews to Group Detail.
- Show representative references as large visual cards with their actual media.
- Show a lightweight thumbnail for every full-population group member when archived remote media is available.
- Keep full-population previews lightweight: only post URL + thumbnail URL are exported, not every slide/media asset.


## 0.8.1 - 2026-10-07

- Fix Structures interaction so clicking a group opens its full population membership instead of silently filtering only the representative reference sample.
- Add full member rows to `candidate_groups.json` with account, post, performance, hook/topic, rank, original URL, and optional representative REF ID.
- Keep representative references explicitly separate from full group population and make sampled refs directly inspectable from the group detail drawer.


## 0.8.0 - 2026-10-07

- Make whole-system understanding the first step of the generated research workspace.
- Add `system.json` with full-dataset account, cadence, performance, dimension, and reference-selection coverage.
- Add `--strategy system` as the default reference sampler: cover accounts first, then balance performance, structural novelty, and account concentration.
- Add `--strategy account-balanced` for near-even per-account sampling while retaining `--strategy top` for later exploitation.
- Build candidate structures from the full reference population instead of only the selected reference sample.
- Redesign the UI as System → Accounts → Structures → References → Compare → Selected.
- Surface largest-account share, account coverage, reference counts per account, and dimension coverage so sample bias is visible.
- Rename shared media helpers around the Reference Workspace.
- Remove the legacy Showcase commands, server, static bundle, docs, tests, and workspace directory.
- Keep `selected.json` as the explicit curated handoff into Creative Bank.


## 0.7.0 - 2026-10-07

- Upgrade downstream handoff to `creative-reference-pack-v2`.
- Reuse existing slideshow Vision `analysis_json`; no Vision rerun is required.
- Export per-reference `details/REF-xxxx.json` with slide-level sequence, hook, product, CTA, visual evidence, confidence, and a deterministic blueprint.
- Add explicit remote/local/hybrid media manifests for production reference review.
- Generate a self-contained Reference Workspace with References, Groups, Compare, and Selected views.
- Add browser-side `selected.json` export for downstream Creative Bank curation.
- Add `creative-research references --open` to serve the generated workspace locally.
- Make remote media the default for reference extraction while retaining copy/hybrid modes.
- Keep Showcase as an optional research/presentation surface rather than the production reference workflow.

## 0.6.0 - 2026-10-07

- Add `rank-posts` for account-relative, breakout, save-rate, and balanced ranking.
- Add `extract-references` to export portable ranked reference packs from `creative_master`.
- Add `query` for explicit table filtering without ad-hoc notebooks.
- Add `group-references` for descriptive candidate grouping without assigning creative families.
- Add `data/07_exports/` as the canonical downstream handoff workspace.
- Extend showcase exports with optional reference-pack matching, `references.json`, REF badges, and a selected-references view.
- Keep downstream hypotheses, experiments, learnings, and playbooks outside this repository.

## 0.5.2 - 2026-10-07

- Bundle the showcase UI as package static files and copy it into every showcase export.
- Add `creative-research showcase` with `--open`, `--host`, `--port`, and `--dir` options.
- Make `data/06_showcase/` a self-contained static site that can be served locally or deployed as-is.
- Overwrite packaged UI files and clear stale generated media assets on every export.
- Make showcase metadata and media notices dataset/mode aware.
- Explicitly package static showcase resources in the wheel and sync the project version in `uv.lock`.

## 0.5.1 - 2026-10-06

- Add opt-in remote, copied, and hybrid media modes for showcase exports.
- Reuse archived TikTok/CDN media URLs and support anonymized local fallback assets.
- Add `--media-limit` to cap media payload size for dashboard demos.
- Update AI Studio prompt to render image cards and inline video previews when available.
- Add deterministic media-export tests and re-identification caveats.

## 0.5.0 - 2026-10-06

- Add `export-showcase` for public-safe dashboard / AI Studio bundles.
- Anonymize creator identities and omit raw analysis/media paths by default.
- Add account, timeline, dimension, and post-level showcase JSON exports.
- Generate a ready-to-use AI Studio Build prompt with each export.
- Add deterministic exporter tests and public-showcase documentation.

## 0.4.0 - 2026-10-06

- Breaking rename from the project-specific package/CLI to generic `creative-research`.
- Rename Python package to `creative_research`.
- Rename project-root environment variable to `CREATIVE_RESEARCH_PROJECT_ROOT`.
- Remove project-specific product-family values from Vision schemas.
- Replace tracked real account lists with fake example configuration.
- Generalize documentation, migration instructions, output examples, and stage help text.
- Keep the evidence pipeline reusable across independent public creative-research projects.

## 0.3.1 - 2026-10-06

- Fix `doctor` environment-check regression.
- Add regression coverage for legacy master validation.

## 0.3.0

- Add deterministic test suite for core pipeline contracts.
- Add master validation, portable paths, schema metadata, CI, package build checks, and critical Ruff linting.
