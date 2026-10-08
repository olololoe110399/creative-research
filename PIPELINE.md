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
                                      |
                    +-----------------+-----------------+
                    |                                   |
                    v                                   v
             build-warehouse                    extract-references
                    |                                   |
                    v                                   |
       operators/accounts/posts                         |
       creative_analysis/sequence                       |
                         --strategy system (default)
                                      |
                   +------------------+------------------+
                   |                                     |
                   v                                     v
             full system map                       representative refs
              system.json                           details/REF-*.json
                   |                                     |
                   +------------------+------------------+
                                      |
                                      v
                            Reference/System Workspace
                       System -> Accounts -> Structures
                       -> References -> Compare -> Selected
                                      |
                                      v
                                selected.json
                                      |
                                      v
                                creative-bank
```

## Sources of truth

1. Raw scrape JSON/JSONL: collected metadata evidence.
2. Local media: creative pixel/video evidence.
3. Vision output: interpretation layer, not raw truth.
4. `creative_master`: normalized, validated compatibility evidence interface.
5. Operator warehouse tables: canonical operator/account/post/analysis/sequence interfaces derived offline from the existing master and Vision evidence.
6. Reference Workspace: a generated decision surface over the evidence, not a new truth source.

## Invariants

- Raw scrape runs are immutable.
- Performance metrics are not shown to Gemini during creative interpretation.
- Every derived stage is reproducible from the stage immediately above it.
- Building the operator warehouse never scrapes TikTok or calls Vision.
- `creative_master` has one row per unique `account+post_id`.
- Stable canonical post IDs are deterministic and shared with the Reference Workspace.
- By default every observed account must map to a manually maintained operator registry entry.
- Multiple accounts from one operator are not treated as independent validation.
- Reference sampling must expose account coverage and sampling concentration.
- System mapping uses the full observed dataset/reference population before a small reference sample is inspected.
- Candidate structures are descriptive; creative-family promotion happens downstream.
- Raw Vision `analysis_json` is normalized before handoff.
- Only explicitly selected references proceed to Creative Bank.
