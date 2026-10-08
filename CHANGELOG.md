# Changelog

## Unreleased

- Add a verified operator registry backed by Python 3.11 TOML parsing.
- Add `build-warehouse` to backfill operator/account/post/creative-analysis/sequence tables from the existing `creative_master` without scraping or rerunning Vision.
- Reuse the Reference Workspace stable `POST-...` identity scheme for canonical post IDs.
- Keep `creative_master` and the existing Reference Workspace backward compatible.
- Add `analyze-performance` for account/operator/global historical performance percentiles and baselines.
- Add `analyze-cadence` for account-level and cross-account operator posting chronology, daily activity, and cadence summaries.
- Add `data/06_analytics/` as the deterministic analytics layer between canonical evidence and future strategy inference.
- Add `build-families` for deterministic operator-scoped creative-family candidates using existing Vision features and ordered sequence evidence.
- Preserve every post through singleton families and retain per-member similarity evidence, origin post, representative post, cohesion, lifecycle, cross-account coverage, and relative-performance summaries.
- Add `calibrate-families` to measure language-independent structural similarity, existing Vision descriptive-text similarity, and current production-family scores without mutating family assignments.
- Export threshold distributions and a stratified review CSV so multilingual/paraphrased family clustering can be calibrated from real data instead of blindly lowering thresholds.
- Speed up `calibrate-families` with structural candidate blocking, semantic upper-bound pruning, blocker-recall diagnostics, and progress output so large operator datasets do not appear hung.
- Add `preview-families-v2` to test conservative language-aware strong/bridge gates and anchor-constrained clustering against calibration pairs without replacing production families.
- Tighten same-language family-v2 preview seeds/bridges with hook/topic coherence gates after real review found broad same-taxonomy false positives, while leaving cross-language translation gates unchanged.
- Add opt-in `judge-family-candidates` with deterministic candidate selection, structured Gemini semantic judgments, pair/evidence/model cache keys, dry-run token/cost planning, hard pair/API-call/output caps, and actual usage reporting.
- Let `preview-families-v2` consume confidence-gated AI judgments: high-confidence same-core edges are strong, high-confidence different/thematic-only edges are rejected, and uncertain/low-confidence judgments fall back to deterministic gates.
- Update the AI family judge default to GA `gemini-3.5-flash-lite`, refresh pricing estimates, and fail fast on non-retryable 4xx model/configuration errors instead of sleeping through retries.
- Raise the AI family structured-output cap to 768 tokens, explicitly use minimal Gemini thinking, remove unsupported Gemini-3 sampling tuning, and constrain response verbosity after real responses were truncated at 320 tokens.
- Refine AI family integration after real preview review: exact/translation/paraphrase/hook variants may create strong core-family edges, while `execution_variant` is preserved as semantic/template evidence and cannot seed a core family by itself.
- Export `family_ai_review.csv` with pair hooks/topics and AI decision/reason/confidence for direct human audit without reading Parquet.
- Make AI family judgment artifacts cumulative upserts by pair ID across compatible model/prompt/schema batches, preserving earlier judgments when a later budgeted batch selects a different subset.
- Tighten the AI family judge to prompt/schema v2 after auditing cross-language false positives: add `template_variant`, require true central-idea equivalence for translations, ignore shared app/format/product funnel in the identity test, and enforce decision/relationship consistency in Pydantic.
- Add a second-pass translation verifier that sees only hook/topic/language evidence, independently validates `translation_adaptation`, downgrades mismatches to `template_variant`, and fails closed to deterministic fallback when verification is uncertain or unavailable.
- Add `analyze-propagation` to derive family account entries, cross-account propagation events, origin/sequence account edges, creative-dimension changes, and descriptive account-role evidence.
- Keep propagation chronology explicitly non-causal and defer testing/scaling/conversion strategy labels to later inference.
- Add `analyze-timeline` for monthly/weekly operator/account strategy windows and deterministic adjacent-window change points.
- Add `discover-patterns` for evidence-backed recurring observations across creative performance, cadence, propagation mutation, family reuse, account flow, and timeline shifts.
- Add `pattern_evidence_links.parquet` so every emitted pattern can trace back to supporting/counter posts, families, and accounts.
- Add `infer-strategies` to promote deterministic patterns into reviewable account/operator strategy hypotheses with confidence, counter evidence, alternative explanations, and promotion readiness.
- Add `strategy_pattern_links.parquet` and inherited `strategy_evidence_links.parquet` so every hypothesis can trace through patterns to supporting/counter post, family, and account evidence.
- Add `promote-knowledge` to build typed strategies, rules, lessons, templates, and playbooks with explicit promotion/review status, scope, validity, confidence, exceptions, and lineage.
- Add Parquet + JSONL knowledge catalog/source/evidence-link exports plus an optional local `knowledge_reviews.toml` approval/reject/hold registry.
- Promote creative-family structure templates only from repeated/cohesive families and keep singleton families out of the reusable template bank.
- Add `build-intelligence-workspace` + `intelligence` for a static Overview → Accounts → Timeline → Families → Patterns → Strategies → Knowledge → Evidence research workspace.
- Add browser drill-down from knowledge/strategy/pattern/family layers to canonical post evidence while keeping trust status and counter evidence visible.
- Package and CI-verify a separate lightweight Operator Intelligence Workspace without replacing the creative-selection Reference Workspace.
- Add `intelligence-build` to plan and execute the deterministic post-Vision pipeline with dependency-aware freshness reuse, parameter-provenance checks, dry-run/force controls, and stage slicing.
- Add `quality-audit` for coverage, duplicate-ID, referential-integrity, evidence-lineage, trust-status, workspace-completeness, and stale-stage checks.
- Emit `pipeline_report.json` and `quality_report.json` so automation/downstream consumers can inspect what was reused, rebuilt, blocked, warned, or failed.

## 0.9.1 - 2026-10-07

- Rename machine-selected account/group counts to **Suggested** so they are not confused with human Selected posts.
- Add Group language filter and rank/views/save sorting.
- Add **Select visible** for filtered group results with confirmation for large selections.
- Keep duplicate selection controls in sync and visually mark selected group rows.


## 0.9.0 - 2026-10-07

- Upgrade the handoff contract to `creative-reference-pack-v3`.
- Give every post in the reference population a stable `POST-xxxxxx` item ID and lightweight normalized Vision detail.
- Keep `REF-xxxx` as Suggested examples only; users can now inspect and select any full-population post from a Structure group.
- Add `population.json` for UI browsing and `population.jsonl` for downstream Creative Bank import.
- Add actual thumbnails to full-population Group Detail and large media cards for Suggested examples.
- Add group search/account filters, per-row selection, Select suggested, and Clear group selection.
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
