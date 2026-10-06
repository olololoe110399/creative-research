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


## Optional media assets

For a more visual dashboard, media can be exported explicitly.

Thumbnail cards for the 100 highest-ranked posts:

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-media \
  --media thumbnails \
  --media-limit 100
```

For selected video posts, copy the local video files too:

```bash
uv run creative-research export-showcase \
  data/05_master/creative_master.parquet \
  --out data/06_showcase-media \
  --media previews \
  --media-limit 100
```

The output adds anonymized asset names such as:

```text
assets/thumbnails/post-0001.jpg
assets/videos/post-0042.mp4
```

and `posts.json` receives `thumbnail_path` / `video_path` only when an asset was copied.

`--media-limit` ranks posts by global view percentile/views. Use `0` to export media for every post.

Media is off by default because images/video can make public-source posts recognizable even when creator names and post IDs are removed. Use media exports deliberately for private demos or curated public showcases.
