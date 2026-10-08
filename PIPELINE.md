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
              analyze-propagation
                       |
                       v
        cross-account propagation
        + account role evidence
                       |
             +---------+---------+
             |                   |
             v                   v
       analyze-timeline     discover-patterns
             |                   ^
             v                   |
       strategy windows           |
       + change points -----------+
             |                   |
             +---------+---------+
                       |
                       v
                infer-strategies
                       |
                       v
        strategy hypotheses
        + counter-evidence
        + alternative explanations
                       |
                       v
              promote-knowledge
                       |
                       v
        data/07_knowledge/
      strategies / rules / lessons
      templates / playbooks
      + source/evidence lineage
                       |
                       v
      build-intelligence-workspace
                       |
                       v
       Operator Intelligence Workspace
     Overview -> Accounts -> Timeline
     -> Families -> Patterns -> Strategies
     -> Knowledge -> Evidence
                       |
                       v
                 quality-audit

intelligence-build wraps the deterministic path from
build-warehouse through workspace + audit and reuses
fresh outputs by explicit dependency/freshness checks.
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
9. Propagation analytics: observed family entries/movement across verified operator accounts plus descriptive account-role evidence.
10. Strategy timeline: fixed historical operator/account windows with deterministic adjacent-window change points.
11. Evidence patterns: recurring observations with sample/effect metrics and explicit post/family/account evidence links.
12. Strategy hypotheses: deterministic pattern promotion with confidence, counter evidence, alternative explanations, and inherited evidence lineage.
13. Knowledge bank: typed strategies/rules/lessons/templates/playbooks with promotion/review status and inherited source/evidence lineage.
14. Operator Intelligence Workspace: generated research surface over warehouse/analytics/knowledge with cross-layer evidence drill-down.
15. Quality audit: freshness, coverage, duplicate-ID, referential-integrity, lineage, trust-status, and workspace-completeness checks.
16. Reference Workspace: generated creative-inspection/selection surface over the evidence, not a new truth source.

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
- Propagation means later observed appearance inside a family; it is not causal proof.
- Account-role evidence remains descriptive until a later strategy inference stage.
- Strategy change points identify measurable shifts; they do not name the business strategy.
- Patterns always set `causal_claim=false` and remain observations until promoted later.
- Strategy inference never turns a hypothesis into a fact; hypothesis rows also keep `causal_claim=false`.
- Strategy hypotheses must preserve supporting/counter pattern links, alternative explanations, and inherited evidence lineage.
- Knowledge promotion never removes caveats, counter evidence, scope, time validity, or source lineage.
- Rejected/held knowledge is retained for audit and must not be treated as active guidance.
- Review candidates should not drive high-impact automation until approved or otherwise explicitly accepted downstream.
- Creative templates require repeated family evidence; singleton families never become templates.
- Operator Intelligence Workspace only materializes existing outputs; it never creates or mutates evidence/analytics/knowledge.
- `intelligence-build` starts at `creative_master`; it never invokes scraping or Vision stages.
- Orchestration freshness checks include data mtimes plus parameter provenance for operator registry, timezone, and knowledge-review registry.
- Rebuild propagation follows explicit data dependencies rather than command order.
- Quality audit failures represent broken/missing integrity or materially incomplete required coverage; warnings must never be converted into fabricated data.
- Knowledge trust status must remain visible in the workspace so rejected/hold/review candidates are not confused with active guidance.
- Pattern evidence must remain traceable to stable post/family/account IDs.
- `creative_master` has one row per unique `account+post_id`.
- Stable canonical post IDs are deterministic and shared with the Reference Workspace.
- By default every observed account must map to a manually maintained operator registry entry.
- Multiple accounts from one operator are not treated as independent validation.
- Reference sampling must expose account coverage and sampling concentration.
- System mapping uses the full observed dataset/reference population before a small reference sample is inspected.
- Reference candidate structures remain descriptive and independent from the operator-level family analytics.
- Raw Vision `analysis_json` is normalized before handoff.
- Only explicitly selected references proceed to Creative Bank.
