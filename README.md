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
-> system/reference workspace
```

The operator warehouse is intentionally built before strategy inference. Future stages can derive cadence, relative performance, creative families, cross-account propagation, strategy periods, patterns, rules, lessons, templates, and playbooks from these canonical tables. Those future knowledge assets must retain evidence lineage instead of being unsupported LLM summaries.

Brief/variant production and first-party experiment outcomes remain downstream concerns.

## Test philosophy

Tests are deterministic and do not call TikTok, Apify, or Gemini.

```bash
uv run ruff check .
uv run pytest --cov=creative_research --cov-report=term-missing
```
