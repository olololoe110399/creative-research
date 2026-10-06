# Public showcase export

\`creative-research export-showcase\` converts a validated
\`creative_master\` into a small JSON bundle designed for dashboards,
demos, and AI Studio Build.

The exporter is **share-safe by default**:

- creator identities are replaced with deterministic aliases such as
  \`Creator 01\`
- raw \`post_id\`, URL, media paths, and raw Vision \`analysis_json\`
  are never included by default
- free-text fields such as hook text and creative formula are excluded
  by default
- metrics and normalized creative taxonomy are preserved for
  visualization

## Export

\`\`\`bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase
\`\`\`

Outputs:

\`\`\`text
data/06_showcase/
├── overview.json
├── accounts.json
├── timeline.json
├── dimensions.json
├── posts.json
├── manifest.json
└── AI_STUDIO_PROMPT.md
\`\`\`

Upload the five JSON data files plus \`AI_STUDIO_PROMPT.md\` to Google
AI Studio Build.

## Opt-in fields

For a private dashboard, identities or model-derived free text can be
explicitly included:

\`\`\`bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-private \
  --include-identities \
  --include-text
\`\`\`

Even with both flags enabled, the exporter never includes
\`analysis_json\` or \`source_media_path\`.

## Interpretation

The default export reduces accidental disclosure but does not guarantee de-identification; exact metrics can still make public-source posts recognizable.\n\nThe bundle is evidence for this dataset, not a claim about the platform
as a whole. Dashboard copy should use language such as
“observed in this dataset” and should show sample size beside
comparisons.


## Optional media

The exporter supports four media modes:

```text
none    JSON only
remote  scraped TikTok/CDN URLs only
copy    local copied assets only, plus canonical post URL
hybrid  remote URLs + copied local fallback assets
```

### Remote mode

This is the lightest option for AI Studio demos:

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-remote \
  --media remote \
  --media-limit 100
```

The exporter reads the archived `raw.json` / `meta.json` for each post and may add:

```text
post_url
thumbnail_url
slide_urls[]
video_url
video_fallback_urls[]
```

For slideshow posts it prefers `slideshowImageLinks[].tiktokLink` and falls back to `downloadLink`.
For covers it prefers `videoMeta.originalCoverUrl` and falls back to the archived cover URL.
For video it reuses direct play/download URLs found in the archived raw record.

Remote CDN URLs can expire or reject hotlinking later. They are convenient, not durable storage.

### Copy mode

For a more durable deployed showcase:

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-copy \
  --media copy \
  --media-limit 50
```

This copies local media to anonymized paths such as:

```text
assets/thumbnails/post-0001.jpg
assets/videos/post-0042.mp4
```

and adds `thumbnail_path` / `video_path` to `posts.json`.

### Hybrid mode

For the best UX when deploying a showcase:

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-hybrid \
  --media hybrid \
  --media-limit 100
```

The dashboard should try remote media first and fall back to copied local assets when a CDN URL fails.

`--media-limit` ranks posts by global view percentile/views. Use `0` for all posts.

Any media mode can make public-source posts recognizable even when creator names and post IDs are omitted, so media exports are not marked as share-safe defaults.
