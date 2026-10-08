# Creative Research

Reusable evidence and operator-intelligence pipeline for reverse-engineering public creative/distribution systems.

The repository keeps raw evidence immutable, preserves existing Vision analysis, and now adds an operator-aware warehouse foundation:

```text
verified operator
  -> public accounts
  -> raw evidence + media
  -> Vision interpretation
  -> validated creative_master
  -> operator-aware canonical tables
  -> whole-system map / reference workspace
  -> later analytics, patterns, strategies, rules, lessons, templates, playbooks
```

The goal is not a generic analytics dashboard. It is a durable research base where conclusions can eventually be traced back to the posts and Vision evidence that support them.

## Requirements

- Python 3.11+
- `uv`
- `ffprobe` optional but useful for video metadata
- `APIFY_TOKEN` only for scraping / rare media fallback
- `GEMINI_API_KEY` only for Vision stages

## Setup

```bash
uv sync --all-groups
uv run creative-research doctor
uv run creative-research init
uv run pytest
```

Never commit real API keys or research datasets.

## CLI

```text
scrape
select-accounts
prepare-media
manifest-slides
vision-slides
download-videos
vision-videos
build-master
build-warehouse
analyze-performance
analyze-cadence
build-families
analyze-propagation

rank-posts
extract-references
query
group-references
references

init
doctor
status
validate
adopt
version
```

## Workspace

```text
data/
├── 00_raw/apify/             # immutable scrape runs
├── 01_selected/targets/      # selected target-account data
├── 02_media/tiktok/          # archived source pixels/video
├── 03_manifests/slides/
├── 03_video_media/
├── 04_vision/slides/
├── 04_vision/videos/
├── 05_master/                # creative_master + operator-aware canonical tables
├── 06_analytics/             # deterministic performance + cadence analytics
└── 07_exports/               # generated system/reference workspaces
```

## Canonical evidence pipeline

### 1. Scrape

```bash
uv run creative-research scrape \
  config/target_accounts.txt \
  --out data/00_raw/apify/run-001
```

### 2. Select accounts

```bash
uv run creative-research select-accounts \
  --sources data/00_raw/apify/run-001 \
  --accounts creator_alpha creator_beta creator_gamma \
  --out data/01_selected/targets
```

### 3. Archive media

```bash
uv run creative-research prepare-media \
  data/01_selected/targets \
  --out data/02_media/tiktok
```

### 4. Build slideshow manifest

```bash
uv run creative-research manifest-slides \
  data/02_media/tiktok \
  --out data/03_manifests/slides
```

### 5. Vision: slideshows

```bash
uv run creative-research vision-slides \
  data/03_manifests/slides/full_manifest.csv \
  --out data/04_vision/slides \
  --model gemini-3.5-flash-lite
```

Performance metrics are not shown to Gemini during creative interpretation.

### 6. Download + analyze videos

```bash
uv run creative-research download-videos \
  data/02_media/tiktok \
  --out data/03_video_media

uv run creative-research vision-videos \
  data/03_video_media/video_manifest.csv \
  --out data/04_vision/videos \
  --model gemini-3.8-flash
```

### 7. Build master

```bash
uv run creative-research build-master \
  --slides data/04_vision/slides/creative_study_v2.parquet \
  --videos data/04_vision/videos/creative_video_study.parquet \
  --out data/05_master

uv run creative-research validate
```

`creative_master` remains the backward-compatible normalized evidence interface.

### 8. Backfill the operator-aware warehouse

No TikTok scrape and no Gemini call are required. Create a local verified operator registry from the fake example, map every researched account to its manually verified operator, then backfill the existing master:

```bash
cp config/operators.example.toml config/operators.toml
# edit config/operators.toml with your locally verified account ownership

uv run creative-research build-warehouse \
  data/05_master/creative_master.parquet \
  --operators config/operators.toml \
  --out data/05_master
```

This writes:

```text
data/05_master/
├── creative_master.parquet       # unchanged compatibility interface
├── operators.parquet
├── accounts.parquet
├── posts.parquet
├── creative_analysis.parquet
├── creative_sequence.parquet
└── warehouse_report.json
```

`creative_sequence` normalizes existing slideshow `slides[]` and video `timeline[]` analysis so the old Vision work becomes reusable data instead of being rerun. Stable `POST-...` identifiers use the same identity scheme as the Reference Workspace.

By default the command fails if an observed account is not present in the verified operator registry. Use `--allow-unmapped` only for intentionally exploratory datasets.

### 9. Build historical performance baselines

This stage uses the metrics already stored on the researched posts. It does not scrape again and does not require realtime snapshots.

```bash
uv run creative-research analyze-performance \
  data/05_master/posts.parquet \
  --out data/06_analytics
```

It writes:

```text
data/06_analytics/
├── post_performance.parquet
├── account_performance_baselines.parquet
├── operator_performance_baselines.parquet
└── performance_report.json
```

For each post, the analytics layer calculates account-relative, operator-relative, and global percentiles for views/likes/comments/shares/saves, plus ratios against account/operator medians. This lets a 100k-view post be interpreted differently on a small account versus a large account.

The values describe the historical dataset you collected. They are not realtime growth curves.

### 10. Build posting cadence

```bash
uv run creative-research analyze-cadence \
  data/05_master/posts.parquet \
  --out data/06_analytics \
  --timezone UTC
```

Choose the analysis timezone that makes sense for the operator when interpreting posting hour/day. The original timestamp remains preserved in UTC.

This writes:

```text
data/06_analytics/
├── posting_cadence.parquet
├── account_activity_daily.parquet
├── operator_activity_daily.parquet
├── account_cadence_summary.parquet
├── operator_cadence_summary.parquet
└── cadence_report.json
```

Cadence is calculated at both levels:

- **account** — gaps between posts on the same account, posts/day, common posting hours;
- **operator** — gaps across all verified accounts, neighboring accounts in the posting sequence, and account-switch behavior.

That operator-level chronology is what later stages can use to test hypotheses such as whether one account appears to test ideas before another account reuses them.

Performance and cadence should be joined by stable `post_uid` when studying relationships such as “high-relative-performance posts tend to be followed by longer or shorter posting gaps.” Such relationships are observations/correlations, not proof of causation.

### 11. Build creative families

Creative families identify repeated executions that appear to share the same underlying creative concept.

```bash
uv run creative-research build-families \
  --posts data/05_master/posts.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --sequence data/05_master/creative_sequence.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --out data/06_analytics
```

This writes:

```text
data/06_analytics/
├── creative_families.parquet
├── creative_family_members.parquet
└── creative_families_report.json
```

The family stage is deterministic and does not call an LLM. It compares evidence already extracted by Vision:

- core topic / pain / desired outcome;
- hook wording;
- replicable hook formula;
- creative formula;
- ordered slide/video sequence roles;
- angle, audience, hook technique, format, and product family.

Posts are only grouped within the same verified operator. Unmapped accounts are isolated from each other instead of being treated as one operator.

Every post remains represented. Posts without a sufficiently similar sibling become singleton families. Every non-origin family member stores:

- similarity to the family origin;
- similarity to its nearest family member;
- the nearest supporting `post_uid`;
- component-level matching evidence in `match_reason_json`.

A family therefore means **deterministic candidate for a shared creative concept**, not “proven strategy.” The next stages can use family origin, chronology, cross-account reuse, and relative performance to study propagation and operator behavior.

### 12. Analyze cross-account propagation

After families exist, derive how each family appears across the manually verified accounts of the same operator:

```bash
uv run creative-research analyze-propagation \
  --members data/06_analytics/creative_family_members.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --out data/06_analytics
```

This writes:

```text
data/06_analytics/
├── family_account_entries.parquet
├── cross_account_propagation.parquet
├── account_propagation_edges.parquet
├── account_sequence_edges.parquet
├── account_role_evidence.parquet
└── propagation_report.json
```

The layer records observable facts such as:

- which account first introduced a family;
- when the same family first appeared on another verified account;
- delay from family origin to that account entry;
- nearest prior observed family member/account;
- which creative dimensions changed or stayed the same;
- relative performance of origin and receiving executions;
- how often each account originates versus imports families.

`account_role_evidence` exposes descriptive signals such as `originator_signal`, `receiver_signal`, and `amplifier_signal`. These are **not** final strategy labels. A later inference layer may use repeated evidence to propose hypotheses such as testing/scaling roles, but it must cite these propagation records and supporting posts.

The nearest-prior account sequence is observational chronology only. It must not be interpreted as proof that one account caused another account to publish.

## System-first reference workflow

The default workflow is deliberately **not "take the global top 30"**.

A portfolio may contain stronger/larger accounts. Global top-N selection can make one or two accounts dominate the sample and hide how the wider operator system works.

### Build the workspace

```bash
uv run creative-research extract-references \
  data/05_master/creative_master.parquet \
  --out data/07_exports/study-system \
  --content-type slideshow \
  --rank relative \
  --strategy system \
  --top 30 \
  --media remote

uv run creative-research references \
  --dir data/07_exports/study-system \
  --open
```

### Selection strategies

`--strategy system` is the default.

It:

1. covers each observed account first when sample size allows;
2. then balances account-relative performance;
3. rewards structural novelty across hook, angle, format, product placement, audience, language, and visual type;
4. penalizes repeated sampling from accounts already represented.

This produces **Suggested examples**, not a whitelist and not independent validation. Any post in a Structure group can still be inspected and selected. Multiple accounts operated by one person are still one operator system.

Other modes:

```bash
--strategy account-balanced
--strategy top
```

- `account-balanced`: near-even reference counts per account.
- `top`: raw ranked sample; useful later when exploiting an already-understood structure.

### Generated workspace

```text
data/07_exports/study-system/
├── index.html
├── app.js
├── style.css
├── favicon.svg
│
├── system.json                 # full-master/operator map
├── candidate_groups.json       # structures + full member lists
├── population.json             # all POST items for the browser
├── population.jsonl            # all POST items for downstream import
├── workspace.json              # Suggested REF examples with full media
├── manifest.json
│
├── references.parquet
├── references.csv
├── references.jsonl
│
├── details/
│   └── REF-xxxx.json
└── media/                      # copy/hybrid only
```

No second Vision pass is performed. `details/REF-xxxx.json` is normalized from the existing Vision `analysis_json`.

## What the UI shows

The generated UI is ordered around the actual research decision:

1. **System** — full dataset size, account coverage, content mix, selection bias, creative dimensions.
2. **Accounts** — account roles, posting cadence, performance context, and how many references each account contributes.
3. **Structures** — full-population groups with thumbnails, search/account/language filters, sorting, inspect/compare, and selection for every post.
4. **Suggested** — representative examples the system recommends inspecting first; these are not the only selectable posts.
5. **Compare** — compare 2–4 posts from Suggested, Structures, or Selected and surface exact shared structure.
6. **Selected** — review human-curated posts, see concentration warnings, and export the final selection.

The UI explicitly shows account coverage and largest-account share so sampling bias is visible rather than hidden.

## Reference detail contract

Each POST item selected for downstream work contains:

```text
source/provenance
selection strategy + reason + performance rank
performance metrics

creative
  audience / topic / angle / format
  hook mechanism

sequence[]
  slide position
  role
  overlay text
  visual type/description
  product visibility
  confidence

product
CTA
visual system
proof
attention mechanisms
uncertainty
deterministic blueprint
media manifest
```

Raw `analysis_json` is not handed downstream.

## Handoff to Creative Bank

After understanding the system and inspecting references, use **Selected → Export selected.json**.

Then downstream:

```bash
uv run creative-bank import-references study-001 \
  ../creative-research/data/07_exports/study-system \
  --selection ~/Downloads/selected.json
```

Only the human-curated POST IDs proceed downstream. Suggested REF IDs remain provenance for posts that happened to be in the system sample.

## Media modes

Default:

```bash
--media remote
```

Other options:

```bash
--media none
--media copy
--media hybrid
```

Use `copy` for durable local source assets and `hybrid` when remote-first/local-fallback is useful.

## Useful utilities

Rank without exporting:

```bash
uv run creative-research rank-posts \
  data/05_master/creative_master.parquet \
  --content-type slideshow \
  --rank relative \
  --top 50
```

Explicit filtering:

```bash
uv run creative-research query \
  data/05_master/creative_master.parquet \
  --where "content_type=slideshow" \
  --where "account_views_pct>=0.75" \
  --columns account,post_id,url,hook_text,views,account_views_pct
```

Standalone descriptive grouping:

```bash
uv run creative-research group-references \
  data/07_exports/study-system/references.parquet
```

## Scope and roadmap

The current implemented layers are:

```text
raw evidence
-> Vision interpretation
-> creative_master
-> operator-aware canonical warehouse
-> relative performance + account/operator cadence
-> creative families
-> cross-account propagation + account role evidence
-> system/reference workspace
```

The operator warehouse is intentionally built before strategy inference. Relative performance, historical cadence, deterministic creative-family candidates, and cross-account propagation/account-role evidence are now analytics layers. Future stages can derive strategy periods, patterns, rules, lessons, templates, and playbooks from these canonical tables. Those future knowledge assets must retain evidence lineage instead of being unsupported LLM summaries.

Brief/variant production and first-party experiment outcomes remain downstream concerns.

## Test philosophy

Tests are deterministic and do not call TikTok, Apify, or Gemini.

```bash
uv run ruff check .
uv run pytest --cov=creative_research --cov-report=term-missing
```
