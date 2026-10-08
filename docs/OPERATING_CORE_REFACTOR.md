# Creator Operating Core Refactor — R1 + R3 + R2 module boundaries

## Design: one system, four jobs

The project's new product goal is not a generic researcher dashboard. It is
to turn legally obtained *public* operator evidence into executable original
content briefs, source/rights tasks and real first-party learnings for another
team.

The Lab now has **four top-level destinations**:

| Area | Team activity | Source of truth |
|---|---|---|
| Production | Edit the original hook/caption/individual slides, assign owners, schedule and publish owned-account content | Private operating_state JSON + immutable production kit |
| Asset Library | Source images/sound, document actual rights and obtain editorial signoff | Same private operating_state JSON |
| Results & Learnings | Log measured 24h/72h/7d views/saves/shares, compare to age-matched own baseline, inspect causal limitations and migration records | Same private operating_state JSON |
| Evidence Explorer | Read Research Brief, Creative Library, Account Network, Observed/Inferred/Unknown, canonical original URLs and counterexamples | Immutable materialized Lab JSON |

There is no AI Copilot button, mandatory Human Review, or second
human hypothesis-approval workflow.

## One mutable store

The materialized source is **read-only**: production.json, evidence.json,
families.json, lab.json and production-kit.zip are recreated by the research
pipeline. Team-owned mutable state is independent:

    data/07_knowledge/operating_state/<sha256-operator-id>.json

The file is operator scoped, gitignored, mode 0600, atomically updated with
fsync and protected by a process-level lock. All browser edits use **one
loopback-only, same-origin JSON API**: `GET /api/operating` and
`POST /api/operating`. `GET /api/operating/export` produces a live ZIP with
the generated source evidence **plus** TEAM_STATE.json,
TEAM_EDITED_BRIEFS, TEAM_TASKS.csv, TEAM_ASSET_RIGHTS.csv and
TEAM_OWN_OUTCOMES.csv. The ZIP is generated on demand; it does not change
the source research or commit credentials.

Every mutation requires the current integer `expected_revision`: stale
browser tabs cannot silently overwrite one another.

### Durable source identity

- Recipe work keyed by stable **family_id**, not ephemeral REC-001 position.
- Image/audio state keyed by **family_id + type + scene/role**.
- Publishing tasks use slot ID plus a signature including family, actual
  proposed hook, variant, account and day. Renumbering/replanning cannot
  silently attach an old approval to a new recipe.
- A recipe's source fingerprint includes family ID, representative original
  post, linked posts and the source structure of each slide.
- Existing results reference their actual post and historical signature.
- If the source changes, the UI flags `needs_recheck` and refuses further
  writes. An intentional **recheck** action preserves the full previous
  record in immutable migration history, then resets editorial, rights
  and publication gates. Missing families remain in the orphan listing.

The researcher's initial account grouping is still an explicit pre-scrape
input, not independent proof of another operator's legal identity.

## Production gates

Asset status follows:

    needed → sourced → rights_checked → editorial_checked → ready

Rights validation requires the file/location, actual permission evidence,
an identified team reviewer and license scope explicitly including TikTok.
A team attestation is *not* legal counsel confirmation; the final editorial
check must be independent of a model's inference about the studied operator.
Advance stages must not be skipped. Sources that change reset the status.

Publishing task status:

    draft → in_production → ready → published  (or skipped)

To mark a post ready/published, the team must have separately edited and
editorially checked its original hook/caption/slides **and** cleared every
image and soundtrack belonging to that recipe. Publication requires a
genuine owned TikTok post URL and timezone-aware ISO timestamp.

Results store actual 24h/72h/168h snapshots, a user-supplied same-age own
baseline, saves/shares, post link and notes. Individual views ratios are
descriptive signals, **not randomized causal conclusions**. Prior results
are preserved with update history.

## Historic data is retained without creating two writable systems

The old `data/07_knowledge/experiment_plans/` files are imported as
**read-only legacy hypothesis-level selections** when a team state first
materializes. The normal Lab no longer writes through `/api/experiments`
(HTTP 410 when legacy not explicitly injected by compatibility consumers).

An old production.json containing user CSV results is migrated to
`legacy_results` **BEFORE** being replaced by a new workspace build. Those
older metrics may not be age-matched; they are displayed as historical
unverified items, separate from new outcomes, rather than silently deleted
or falsely treated as validated. Duplicate rebuilds do not duplicate history.

CLI imports previously supported by `production-kit` now write to the
**same** private state:

    uv run creative-research production-kit \
      --own-results-csv path/to/own_age_matched_results.csv

    uv run creative-research production-kit \
      --clearance-csv path/to/team_rights_attestation.csv

Imports are atomic per file. Invalid rows fail without partial file writes.
A positive rights CSV import reaches `rights_checked` but does not
automatically complete editorial review. Own-results CSV must identify a
real TikTok URL, valid pilot account/recipe, timestamp with timezone, post
age 24/72/168h and positive same-age baseline.

The private state is not wiped by running:
    uv run creative-research intelligence-build \
      --operators config/operators.toml --from-stage workspace --force

## Smaller functional modules

`production_kit.py` used to combine copying templates, post ranking,
raw scrape metadata, licensing, outcomes, audit, CSV, Markdown and ZIP.
It now delegates to:

- `production_fields.py`: common numerical/text normalization and
  source percentile access.
- `production_copy.py`: source-aware Vietnamese editorial archetypes
  and original visual prompts.
- `production_source_bank.py`: offline caption/hashtag/sound extraction
  from existing public raw files. Never grants rights.
- `production_quality.py` and `production_contracts.py`: one handoff
  schema, limits and source/rights safety invariants.
- `production_handoff.py`: deterministic CSV/Markdown/ZIP writer.
- `production_kit.py`: family/recipe selection, account blueprint and
  candidate calendar generation.
- `operating_state.py`: **only mutable first-party workflow** (stored
  outside the regenerated JSON).
- `operating_endpoints.py` / `http_local.py`: strict local API and
  reusable security separate from Gemini.
- UI split: `production_ui.js` read-only research-derived presentation,
  `operating_ui.js` user edits, outcomes and stateful task forms;
  `research_ui.js` bounded Evidence Explorer projections.

The legacy `ai_research.py`, human-reviewed knowledge catalog and older
reference workspace are retained for backwards compatibility, **not**
part of the production UI. Their existing consumer references/tests
still work; deleting them prematurely would destroy lineage.

## Acceptance and rollout

This is a stacked PR **based on PR #45**. It must not be merged into main
before its base is merged, unless explicitly rebased/reviewed. CI checks
Ruff, Python 3.11/3.13, source and rights guardrails, ZIP, Node UI smoke and
wheel packaging.

To preview:

    git fetch origin
    git switch refactor/creator-operating-core
    uv sync --all-groups
    uv run creative-research intelligence-build \
      --operators config/operators.toml --from-stage workspace --force
    uv run creative-research lab --open

The generated source ZIP at `production-kit.zip` is intentionally a
research-only draft. The button **Download live team handoff ZIP** obtains
the same public sources and current team-owned work from
`/api/operating/export`; use that ZIP when handing the project to another
team. Neither file contains a verified/cleared source media download.

**Remaining work outside this refactor:** a canonical one-time music/caption/
hashtag warehouse index instead of rescanning existing JSONL per refresh;
a unified calibrated multi-language family judge with measured false-split
recall; live platform availability checks for commercial music; a publishing
API; controlled cross-post inference. These need new datasets and independent
acceptance, not fabricated confidence claims.
