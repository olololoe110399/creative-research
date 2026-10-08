# Operator Production Kit v1 — Evidence → Creator Team Handoff

**North Star:** A researcher selects an operator; the system audits public
creative evidence and delivers an operational handoff to a second team.
The receiving team can open an account blueprint, build original slideshow
content from editable Vietnamese drafts, source their own media/sound,
schedule controlled test variants, and record actual outcomes WITHOUT
re-researching the original TikTok operator.

This is a **public-evidence reverse engineering** workflow. It is NOT
access to a private account/network, proof of the studied operator's intent,
or authorization to republish its copyrighted material.

## 1. Build from the existing corpus; no new scrape or Gemini call

    git switch feat/operator-production-handoff-v1
    uv sync --all-groups

    uv run creative-research intelligence-build \
      --operators config/operators.toml \
      --from-stage workspace --force

    uv run creative-research quality-audit
    uv run creative-research outcome-audit
    uv run creative-research lab --open

The normal workspace build now also generates:

    data/07_exports/operator-intelligence/
      production.json
      production-kit.zip
      index.html (Production Kit is the default tab)

The production kit is generated from the same canonical evidence.json,
families.json and accounts.json as the research UI. It does not invent
source IDs, fetch social sites, start AI review or modify historical posts.

If local Apify JSONL files still exist under data/00_raw/apify, the
workspace builder automatically scans them (bounded offline pass) and
recovers music IDs/names, source captions and hashtag frequencies from
**all matched canonical posts**. The derived sound/caption bank retains
source URLs/IDs and remains a research reference only.

For other archived raw roots or customized handoff sizes:

    uv run creative-research production-kit \
      --workspace data/07_exports/operator-intelligence \
      --raw-root data/01_selected/targets \
      --recipes 24 --days 30

Constraints: 1–40 recipes; 1–90 content-plan days. The default is
16 distinct editorial candidates across repeated families and promising
single-post examples, plus a 30-day publishing experiment. Rebuilds
overwrite the generated plan/ZIP; preserve any team edits outside it.

## 2. What the team ZIP contains

| File | Exactly what it is for |
|---|---|
| START_HERE.md | Safe handoff order, responsibilities and publish blockers |
| ACCOUNT_BLUEPRINTS.md | Two independently owned pilot accounts: positioning, audience, bio, avatar brief, content pillars and setup checklist |
| CONTENT_PLAN.csv | Day 1–30 plan: account slot, selected recipe, actual hook A/B draft, publishing slot, single changed variable, metrics and production gate |
| briefs/REC-xxx.md | Per-recipe original hook draft, per-slide overlay, original-image direction, visual search queries and source TikTok links |
| SOURCE_EVIDENCE.csv | Exact canonical post IDs/URLs, per-account percentiles, views, observed source hooks and source counts |
| ASSET_BANK.csv | Image and music sourcing tasks, source refs, visual query and explicit rights/publish readiness fields |
| SOUND_BANK.csv | Only real music identifiers/names recovered from raw scrape, if present. License unverified |
| CAPTION_BANK.csv | Observed original captions (reference only), with source post links |
| HASHTAG_BANK.csv | Observed hashtag counts and example source IDs; not a relevance guarantee |
| SUSPECTED_FALSE_SPLITS.csv | Conservative same-hook, same-product, same-sequence cross-account singleton candidate pairs; NOT automatically merged |
| ASSET_CLEARANCE_TEMPLATE.csv | Editable team-side rights evidence sheet for images/sound/font |
| OWN_RESULTS_TEMPLATE.csv | Data-entry sheet for own account post results (24h/72h/7d) |
| OWN_EXPERIMENT_RESULTS.csv | First-party results after importing a completed sheet |
| QUALITY_REPORT.json | Machine evidence, rights and handoff contract checks |
| LESSONS.md | Observed format/reuse facts, bounded operational tests, and limits |
| PRODUCTION.json | Complete machine-readable handoff with all references |

The ZIP DOES NOT contain ripped media, copied source music or a guaranteed
license. For any recipe, the source original overlay is a clearly marked
reference-only field, next to a newly proposed Vietnamese overlay draft.
The draft must still be fact-checked, customized to the team's authentic
voice and paired with **original or appropriately licensed** assets.

## 3. Editorial workflow, from account to published experiment

**Account owner**
- Read ACCOUNT_BLUEPRINTS.md; own and secure two real accounts. Names and
  avatar ideas are proposals; never impersonate the studied accounts.
- Choose a real audience. Default is Vietnamese study-tips niches; adjust
  for your brand, locale and product before publication.

**Research/editor**
- Choose recipe REC-xxx and open the cited family/post links in the UI.
- Check at least one negative execution and uncertain creative family match,
  including suspected false-split cases.
- Approve the new draft as your own factual content; original operator
  scripts/captions are inspiration only, not ready-to-post files.

**Designer**
- Follow each slide's layout/visual description and image-search query.
- Pinterest searches are for composition inspiration, not content rights.
  Photograph/create original images or check the actual original stock
  license, credit/usage and permission for your intended use.

**Publishing/account operator**
- Pick an actual cleared sound from your permitted catalog. A scraped
  musicId alone does not grant commercial or regional permission.
- Attach sound, image and any branded font rights records.
- The kit cannot mark any slot auto-publishable: content, claims,
  disclosure and platform rules still need your own signoff.
- Log the actual published URL, time and variation.
- Do not bulk-repost, spam coordinated duplicates or impersonate others.

**Measurement**
- Compare variants A and B on the SAME pilot account with unchanged
  content structure, publishing slot and visual style where possible.
- The supplied two hooks differ and the draft says what to hold constant.
- Collect views, saves, shares at identical **post ages**: 24h, 72h,
  7d. These require NEW first-party tracking; historical snapshot views
  are not time-normalized.
- Review at least five comparable A/B pairs before inferring a direction,
  or stop sooner for rights/accuracy problems. Five is an EXPLICIT
  PROPOSED experiment rule, NOT something the operator was proven to use.
- Include failures and source-quality errors in lessons.

## 4. Team-supplied rights clearance

After your team has sourced files and permission evidence, copy the
headers in ASSET_CLEARANCE_TEMPLATE.csv and fill one row for each asset
you want to attest. Required fields:

    asset_id,rights_status,file_or_licensed_source_url,
    license_evidence_url,license_scope,verified_by,verified_at

Use only the allowed marker:

    team_attested_licensed

A valid positive attestation also requires a file/location, rights evidence,
a named reviewer and an explicit scope including TikTok.

Re-export:

    uv run creative-research production-kit \
      --clearance-csv path/to/rights_attestations.csv

This records TEAM attestation, not independent verification by the app.
Even fully attested rights do not auto-approve copy/claims or publish.

## 5. Import actual first-party results

Use OWN_RESULTS_TEMPLATE.csv:

    recipe_id,account_slot,published_url,posted_at,
    measurement_age_hours,views,saves,shares,
    account_median_views,notes

Then:

    uv run creative-research production-kit \
      --own-results-csv path/to/real_post_results.csv

The kit records outcome metrics and comparison to your own baseline,
with evidence_origin = first_party_team_reported_not_scraped_operator.
It does NOT claim that a one-post result proves causality or the
studied operator's playbook.

Note: for truly controlled comparisons, your entered account median
should come from your own recent cohort at the same observation age.
The app does not certify input accuracy. Every new kit run without
the completed CSV starts a new output snapshot, not a persistent
external experiment database.

## 6. Evidence ranks and missing data

Family examples are ranked to help editorial inspection by:
- repeated/cross-account execution coverage;
- account-relative observed views percentile;
- save-rate descriptive signals.

This heuristic is **not a statistical success probability**. The kit
includes both poor and strong members of a selected family where available.
Singles are explicitly labeled single_observed_example.

Possible false splits are surfaced as candidates, not silently merged.
Matching normalized source hooks and slide roles cannot by itself
certify exact creative identity, and multilingual semantic false splits
require additional family-judge research upstream.

Account blueprints, the Vietnamese drafting templates and publishing hours
are EXPERIMENT PROPOSALS. The source post/media/analytics remain Observed,
while test→scale internal operator intent and future effectiveness remain
Unknown until new first-party testing provides evidence.

## 7. Acceptance gates / remaining limits

Offline tests assert:
- every recipe is backed by real post IDs/URLs;
- storyboard and image requests exist;
- rights-unverified assets cannot become marked publishable;
- all planned slots link to valid recipe IDs;
- results stay first-party/observational;
- full raw metadata source bank stays unlicensed;
- wheel and Lab UI include the Production Kit;
- Lab navigation does not call Gemini or demand human approval.

The team-ready meaning is **actionable planning & creative briefs ready for
human production**, NOT pre-cleared assets or auto-publishable media.

**Still not in v1:** automatically licensed photo/audio downloads; live
availability/region checks for TikTok tracks; creator-account provisioning
or TikTok publishing; automated A/B causal assessment; a universal
multilingual translation validator; live share/save tracking or a finished
platform-specific video editor.
