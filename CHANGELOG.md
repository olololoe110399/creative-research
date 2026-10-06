# Changelog

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
