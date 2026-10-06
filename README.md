# Creative Research

Reusable evidence pipeline for reverse-engineering public creative/distribution systems.

This repository owns the **market evidence** side only:

```text
public accounts
  -> raw evidence + media
  -> Vision interpretation
  -> validated creative_master
  -> whole-system map
  -> representative reference sample
  -> inspect / compare / select
  -> selected.json
  -> downstream creative-bank
```

The goal is not to build a generic analytics dashboard. The generated UI is a working research surface for understanding an operator's whole content system before choosing examples to adapt downstream.

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
├── 05_master/                # canonical normalized evidence
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

`creative_master` remains the canonical normalized evidence interface.

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

This produces a **representative inspection sample**, not independent validation. Multiple accounts operated by one person are still one operator system.

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
├── candidate_groups.json       # structures from full reference population
├── workspace.json              # representative detailed refs
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
3. **Structures** — descriptive hook × angle × format × product-placement groups across the full reference population.
4. **References** — representative actual executions with media and slide-level Vision detail.
5. **Compare** — compare 2–4 executions and surface exact shared structure.
6. **Selected** — curate only the references worth sending downstream.

The UI explicitly shows account coverage and largest-account share so sampling bias is visible rather than hidden.

## Reference detail contract

Each selected reference contains:

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
uv run creative-bank references import \
  ../creative-research/data/07_exports/study-system \
  --project study-001 \
  --selection ~/Downloads/selected.json
```

Only the human-curated reference IDs proceed to family/brief/experiment work.

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

## Boundaries

This repository ends at:

```text
market evidence
-> system understanding
-> curated reference handoff
```

It does **not** own:

- downstream creative families;
- briefs/variants;
- first-party experiment results;
- validated playbooks;
- product decisions.

Those belong in the downstream Creative Bank/project layer.

## Test philosophy

Tests are deterministic and do not call TikTok, Apify, or Gemini.

```bash
uv run ruff check .
uv run pytest --cov=creative_research --cov-report=term-missing
```
