# Creative Research

Reusable production evidence pipeline for public TikTok creative and distribution research.

The repository intentionally does one job only:

```text
Apify raw data
  -> selected target accounts
  -> local creative media
  -> slideshow/video manifests
  -> Gemini creative interpretation
  -> validated creative_master
  -> ranked reference packs for downstream production
```

It excludes OCR experiments, EDA, notebooks, RAG, agents, and knowledge-bank logic. The optional showcase is a presentation layer over the validated evidence, not an analysis/knowledge layer.

## Requirements

- Python 3.11+
- `uv`
- `ffprobe` optional but recommended for video metadata
- `APIFY_TOKEN` only for scraping / rare media fallback
- `GEMINI_API_KEY` only for Vision stages

## Setup

```bash
uv sync --all-groups
uv run creative-research doctor
uv run creative-research init
uv run pytest
```

Commit `uv.lock` after dependency resolution. Never commit real API keys or research datasets.

## CLI

```bash
uv run creative-research --help
```

Canonical commands:

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
export-showcase
showcase

init
doctor
status
validate
adopt
```

## Production checks

```bash
uv run ruff check .
uv run pytest --cov=creative_research --cov-report=term-missing
uv run creative-research validate
```

`creative-research validate` verifies the master schema, unique `account+post_id` keys, valid content types, nonblank identities, and nonnegative core metrics.

## Workspace

```text
data/
├── 00_raw/apify/             # immutable Apify scrape runs
├── 01_selected/targets/      # selected/merged target-account data
├── 02_media/tiktok/          # local source media
├── 03_manifests/slides/      # slideshow manifest
├── 03_video_media/           # downloaded videos + video manifest
├── 04_vision/slides/         # slideshow Vision outputs
├── 04_vision/videos/         # video Vision outputs
├── 05_master/                # canonical normalized dataset
├── 06_showcase/              # generated self-contained static showcase site
└── 07_exports/               # portable downstream reference packs
```

Generated manifests use project-relative paths whenever possible. Vision readers resolve those paths from `CREATIVE_RESEARCH_PROJECT_ROOT` or the current working directory.

## Example config

Tracked config files are examples only:

```text
config/target_accounts.example.txt
config/reference_accounts.example.txt
examples/data/creative_master.example.csv
```

Create local research files from the examples:

```bash
cp config/target_accounts.example.txt config/target_accounts.txt
cp config/reference_accounts.example.txt config/reference_accounts.txt
```

`config/*.txt` and all real `data/` artifacts are ignored by Git; only explicit `*.example.txt` files and synthetic files under `examples/` should be committed.

## End-to-end pipeline

### 1. Scrape

```bash
uv run creative-research scrape \
  config/target_accounts.txt \
  --out data/00_raw/apify/run-001
```

### 2. Merge/select target accounts

```bash
uv run creative-research select-accounts \
  --sources data/00_raw/apify/run-001 data/00_raw/apify/run-002 \
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

### 5. Analyze slideshows

```bash
uv run creative-research vision-slides \
  data/03_manifests/slides/full_manifest.csv \
  --out data/04_vision/slides \
  --model gemini-3.5-flash-lite
```

Performance metrics are not sent to Gemini; they are joined after interpretation.

### 6. Download video posts

```bash
uv run creative-research download-videos \
  data/02_media/tiktok \
  --out data/03_video_media \
  --cookies-from-browser chrome
```

### 7. Analyze videos

```bash
uv run creative-research vision-videos \
  data/03_video_media/video_manifest.csv \
  --out data/04_vision/videos \
  --model gemini-3.8-flash
```

### 8. Build the canonical master dataset

```bash
uv run creative-research build-master \
  --slides data/04_vision/slides/creative_study_v2.parquet \
  --videos data/04_vision/videos/creative_video_study.parquet \
  --out data/05_master

uv run creative-research validate
```

Outputs:

```text
data/05_master/
├── creative_master.parquet
├── creative_master.csv
├── creative_master.jsonl
└── report.json
```

### 9. Rank and export production references

Use account-relative performance by default so one large account does not dominate selection:

```bash
uv run creative-research rank-posts \
  data/05_master/creative_master.parquet \
  --content-type slideshow \
  --rank relative \
  --top 50
```

Export the selected source material as a portable handoff:

```bash
uv run creative-research extract-references \
  data/05_master/creative_master.parquet \
  --out data/07_exports/study-reference-pack \
  --content-type slideshow \
  --rank relative \
  --top 30
```

The pack contains `references.parquet/csv/jsonl`, `manifest.json`, and `summary.md`. Use `--media copy` only when downstream work needs local source media.

Descriptive grouping is available without assigning creative-family truth:

```bash
uv run creative-research group-references \
  data/07_exports/study-reference-pack/references.parquet
```

Use `query` for explicit filters instead of one-off notebooks:

```bash
uv run creative-research query \
  data/05_master/creative_master.parquet \
  --where "content_type=slideshow" \
  --where "account_views_pct>=0.75" \
  --columns account,post_id,url,hook_text,views,account_views_pct
```

### 10. Build and view the showcase (optional)

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase \
  --media remote \
  --media-limit 0 \
  --include-text \
  --references data/07_exports/study-reference-pack/references.parquet
```

Every export regenerates a self-contained static site in `data/06_showcase/`: the packaged UI template is overwritten with the current version, JSON is rebuilt from `creative_master`, and stale generated media assets are cleared before optional media is exported.

```text
data/06_showcase/
├── index.html
├── app.js
├── style.css
├── favicon.svg
├── overview.json
├── accounts.json
├── timeline.json
├── dimensions.json
├── posts.json
├── references.json
├── manifest.json
└── AI_STUDIO_PROMPT.md
```

Serve it over local HTTP:

```bash
uv run creative-research showcase --open
```

By default, creator identities, raw post IDs/URLs, free text, media paths, raw Vision analysis, and media assets are excluded. Use `--media remote` for scraped TikTok/CDN URLs, `--media copy` for local static assets, or `--media hybrid` for remote media with local fallbacks. See [`docs/SHOWCASE.md`](docs/SHOWCASE.md).

This repository ends at validated evidence, ranked reference handoff, and an optional presentation export. Pattern banks, hypotheses, experiments, and playbooks belong in a separate downstream layer.

## Resume behavior

Long-running stages preserve progress:

- media archive skips existing files
- video downloader skips existing videos
- slideshow Vision caches by schema/model/media SHA1
- video Vision caches analyzed videos

Run the same command again after interruption.

## Test philosophy

Tests are local and deterministic. They do not call Apify, TikTok, or Gemini. Runtime integrations rely on retry/cache behavior while CI tests local pipeline contracts.
