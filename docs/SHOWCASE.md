# Showcase

`creative-research export-showcase` converts a validated `creative_master` into a
self-contained static site under `data/06_showcase/`.

The showcase is a presentation layer only. It does not replace
`creative_master`, add knowledge-bank logic, or change the evidence pipeline.

## Build

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase \
  --media remote \
  --media-limit 0 \
  --include-text
```

Every export:

1. regenerates the JSON datasets,
2. overwrites the packaged UI template with the current version,
3. removes stale generated `assets/`,
4. optionally exports remote/copied/hybrid media,
5. writes a fresh manifest and AI Studio prompt.

Output:

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
├── manifest.json
├── AI_STUDIO_PROMPT.md
└── assets/                 # only for copy/hybrid media when needed
```

The UI source lives inside the Python package at
`src/creative_research/showcase_static/`. Edit the package template, not the
generated copies under `data/06_showcase/`.

## View locally

The site uses `fetch()` to load JSON, so serve it over HTTP instead of opening
`index.html` with `file://`.

```bash
uv run creative-research showcase
```

Default address:

```text
http://127.0.0.1:8765/
```

Open the browser automatically:

```bash
uv run creative-research showcase --open
```

Custom directory/port:

```bash
uv run creative-research showcase \
  --dir data/06_showcase-private \
  --host 127.0.0.1 \
  --port 9000 \
  --open
```

The server validates that the required HTML/CSS/JS and JSON files exist before
starting. It never rebuilds the showcase implicitly.

## Share-safe defaults

With no opt-in flags:

- creator identities use deterministic aliases such as `Creator 01`,
- raw `post_id` and source URLs are omitted,
- raw media paths and Vision `analysis_json` are omitted,
- free-text hook/topic/formula fields are omitted,
- media is disabled.

These defaults reduce accidental disclosure but do not guarantee
de-identification; exact public-source metrics can still make posts recognizable.

## Optional text and identity

For a private showcase:

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-private \
  --include-identities \
  --include-text
```

Even with both flags enabled, `analysis_json` and `source_media_path` are not
exported.

## Media modes

```text
none    no media
remote  scraped TikTok/CDN URLs
copy    copied local assets plus canonical post URL
hybrid  remote URLs plus copied local fallbacks
```

### Remote

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase \
  --media remote \
  --media-limit 0
```

Remote mode reads the already archived `raw.json` / `meta.json`; it does not
refresh TikTok over the network during export.

Possible post fields include:

```text
post_url
thumbnail_url
slide_urls[]
video_url
video_fallback_urls[]
```

Slideshow URLs prefer `slideshowImageLinks[].tiktokLink` and fall back to
`downloadLink`. Covers prefer `videoMeta.originalCoverUrl`. Video URLs are
selected from direct play/download URLs found in the archived raw record.

Remote URLs can expire or reject hotlinking later.

### Copy

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --media copy \
  --media-limit 50
```

Copied assets use anonymized paths such as:

```text
assets/thumbnails/post-0001.jpg
assets/videos/post-0042.mp4
```

### Hybrid

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --media hybrid \
  --media-limit 100
```

The packaged UI prefers remote media and falls back to copied local assets when
available.

Any media mode can make public-source posts recognizable even when creator names
and raw post IDs are omitted.

## Interpretation

The dashboard is descriptive. Copy should say “observed in this dataset,” show
sample size beside comparisons, and avoid causal claims from categorical
associations.
