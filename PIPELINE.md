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
prepare-media
  |
  +---------------------------+
  |                           |
  v                           v
manifest-slides          download-videos
  |                           |
  v                           v
vision-slides             vision-videos
  |                           |
  +------------+--------------+
               |
               v
          build-master
               |
               v
        creative_master
               |
               v
         build-warehouse
               |
       +-------+--------+
       |                |
       v                v
 canonical tables   extract-references
       |                |
       |                v
       |        Reference Workspace
       |
       +------------------------------+
       |                              |
       v                              v
analyze-performance             analyze-cadence
       |                              |
       v                              v
relative performance        account/operator chronology
       |                              |
       +---------------+--------------+
                       |
                       v
                 build-families
                       |
                       v
             creative family candidates
                       |
                       v
          future evidence intelligence
      propagation -> patterns -> strategies
      -> rules -> lessons -> templates
      -> playbooks
```

## Sources of truth

1. Raw scrape JSON/JSONL: collected metadata evidence.
2. Local media: creative pixel/video evidence.
3. Vision output: interpretation layer, not raw truth.
4. `creative_master`: normalized, validated compatibility evidence interface.
5. Operator warehouse tables: canonical operator/account/post/analysis/sequence interfaces derived offline from the existing master and Vision evidence.
6. Performance analytics: deterministic relative baselines over the observed historical metrics.
7. Cadence analytics: deterministic account/operator posting chronology over stored timestamps.
8. Creative families: deterministic candidate groupings of repeated concepts with per-member similarity evidence.
9. Reference Workspace: a generated decision surface over the evidence, not a new truth source.

## Invariants

- Raw scrape runs are immutable.
- Performance metrics are not shown to Gemini during creative interpretation.
- Every derived stage is reproducible from the stage immediately above it.
- Building the operator warehouse or analytics never scrapes TikTok or calls Vision.
- Performance analytics describe the collected historical snapshot; no realtime history is fabricated.
- Cadence preserves UTC timestamps and derives local-time views only from an explicit analysis timezone.
- Performance/cadence relationships are observations, not causal claims.
- Creative families never cross verified operator boundaries.
- Every post remains represented; unmatched posts become singleton families.
- Family membership keeps origin/nearest-member scores and component-level evidence.
- `creative_master` has one row per unique `account+post_id`.
- Stable canonical post IDs are deterministic and shared with the Reference Workspace.
- By default every observed account must map to a manually maintained operator registry entry.
- Multiple accounts from one operator are not treated as independent validation.
- Reference sampling must expose account coverage and sampling concentration.
- System mapping uses the full observed dataset/reference population before a small reference sample is inspected.
- Reference candidate structures remain descriptive and independent from the operator-level family analytics.
- Raw Vision `analysis_json` is normalized before handoff.
- Only explicitly selected references proceed to Creative Bank.
