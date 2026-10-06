# Canonical pipeline

```text
Apify
  |
  v
data/00_raw/apify/<run>/
  |
  v
select-accounts
  |
  v
data/01_selected/targets/
  |
  v
prepare-media
  |
  v
data/02_media/tiktok/                 <- local creative source of truth
  |
  +----------------------+----------------------+
                         |                      |
                         v                      v
                 manifest-slides       download-videos
                         |                      |
                         v                      v
              data/03_manifests/slides  data/03_video_media
                         |                      |
                         v                      v
                   vision-slides          vision-videos
                         |                      |
                         v                      v
                data/04_vision/slides   data/04_vision/videos
                         \                      /
                          \                    /
                           +------ build-master
                                      |
                                      v
                              data/05_master/
                              creative_master.parquet
                                      |
                                      v
                                  validate
```

## Sources of truth

1. Raw scrape JSON/JSONL: collected metadata evidence.
2. Local media: creative pixel/video evidence.
3. Vision output: interpretation layer, not raw truth.
4. `creative_master`: normalized, validated interface for downstream research.

## Invariants

- Raw scrape runs are immutable.
- Performance metrics are not shown to Gemini during creative interpretation.
- Every derived stage is reproducible from the stage immediately above it.
- New manifests use portable project-relative paths when possible.
- `creative_master` has one row per unique `account+post_id`.
- `content_type` is only `slideshow` or `video`.
- Exploratory analysis does not belong in this canonical repository.


## Optional showcase export

After `creative_master` validates successfully, a public-safe presentation bundle can be generated without changing the canonical evidence dataset:

```text
creative_master.parquet
        |
        v
 export-showcase
        |
        v
 data/06_showcase/
 overview.json + accounts.json + timeline.json + dimensions.json + posts.json
```

The export anonymizes creator identities and omits raw analysis/media paths by default. It is intended for dashboards and AI Studio Build, not as a replacement for `creative_master`.
