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
analyze-performance
analyze-cadence
build-families
analyze-propagation
analyze-timeline
discover-patterns
infer-strategies
promote-knowledge
build-intelligence-workspace
intelligence
intelligence-build
quality-audit

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
├── 06_analytics/             # deterministic evidence + intelligence analytics
├── 07_knowledge/             # strategies/rules/lessons/templates/playbooks
└── 07_exports/               # reference + operator intelligence workspaces
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

### 9. Build historical performance baselines

This stage uses the metrics already stored on the researched posts. It does not scrape again and does not require realtime snapshots.

```bash
uv run creative-research analyze-performance \
  data/05_master/posts.parquet \
  --out data/06_analytics
```

It writes:

```text
data/06_analytics/
├── post_performance.parquet
├── account_performance_baselines.parquet
├── operator_performance_baselines.parquet
└── performance_report.json
```

For each post, the analytics layer calculates account-relative, operator-relative, and global percentiles for views/likes/comments/shares/saves, plus ratios against account/operator medians. This lets a 100k-view post be interpreted differently on a small account versus a large account.

The values describe the historical dataset you collected. They are not realtime growth curves.

### 10. Build posting cadence

```bash
uv run creative-research analyze-cadence \
  data/05_master/posts.parquet \
  --out data/06_analytics \
  --timezone UTC
```

Choose the analysis timezone that makes sense for the operator when interpreting posting hour/day. The original timestamp remains preserved in UTC.

This writes:

```text
data/06_analytics/
├── posting_cadence.parquet
├── account_activity_daily.parquet
├── operator_activity_daily.parquet
├── account_cadence_summary.parquet
├── operator_cadence_summary.parquet
└── cadence_report.json
```

Cadence is calculated at both levels:

- **account** — gaps between posts on the same account, posts/day, common posting hours;
- **operator** — gaps across all verified accounts, neighboring accounts in the posting sequence, and account-switch behavior.

That operator-level chronology is what later stages can use to test hypotheses such as whether one account appears to test ideas before another account reuses them.

Performance and cadence should be joined by stable `post_uid` when studying relationships such as “high-relative-performance posts tend to be followed by longer or shorter posting gaps.” Such relationships are observations/correlations, not proof of causation.

### 11. Build creative families

Creative families identify repeated executions that appear to share the same underlying creative concept.

```bash
uv run creative-research build-families \
  --posts data/05_master/posts.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --sequence data/05_master/creative_sequence.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --out data/06_analytics
```

This writes:

```text
data/06_analytics/
├── creative_families.parquet
├── creative_family_members.parquet
└── creative_families_report.json
```

The family stage is deterministic and does not call an LLM. It compares evidence already extracted by Vision:

- core topic / pain / desired outcome;
- hook wording;
- replicable hook formula;
- creative formula;
- ordered slide/video sequence roles;
- angle, audience, hook technique, format, and product family.

Posts are only grouped within the same verified operator. Unmapped accounts are isolated from each other instead of being treated as one operator.

Every post remains represented. Posts without a sufficiently similar sibling become singleton families. Every non-origin family member stores:

- similarity to the family origin;
- similarity to its nearest family member;
- the nearest supporting `post_uid`;
- component-level matching evidence in `match_reason_json`.

A family therefore means **deterministic candidate for a shared creative concept**, not “proven strategy.” The next stages can use family origin, chronology, cross-account reuse, and relative performance to study propagation and operator behavior.

#### Calibrate family discovery before loosening thresholds

For multilingual or heavily paraphrased datasets, do not blindly lower the production threshold. Run the diagnostic calibration stage:

```bash
uv run creative-research calibrate-families
```

It writes:

```text
data/06_analytics/family_calibration/
├── family_calibration_pairs.parquet
├── family_calibration_review.csv
└── family_calibration_report.json
```

The calibration layer does **not** change current family assignments. It separates:

- language-independent structure similarity from fixed Vision taxonomy + sequence roles/visual types;
- descriptive-text similarity from existing Vision topic/pain/outcome/formula/visual descriptions;
- the current production family score.

The report counts high-scoring cross-language/cross-account pairs that the production family layer currently leaves split. The review CSV provides a small stratified set of candidate pairs for human inspection before changing the production family model.

See `docs/FAMILY_CALIBRATION.md` for the scoring contract.

#### Preview the conservative family-v2 gate before production migration

After calibration is available:

```bash
uv run creative-research preview-families-v2
```

This writes:

```text
data/06_analytics/family_v2_preview/
├── family_v2_preview_families.parquet
├── family_v2_preview_members.parquet
├── family_v2_preview_review.csv
└── family_v2_preview_report.json
```

The preview is deliberately conservative:

- new family seeds require a strong pair (default combined score >= 0.80);
- same-language and cross-language pairs use different semantic/structure gates;
- weaker 0.75–0.80 edges can only bridge a post into a family that already has strong evidence;
- every assignment still needs an anchor relationship, preventing unconstrained transitive mega-clusters;
- existing production-family pairs are retained as positive controls.

The preview never overwrites `creative_families.parquet`. Inspect the family-size distribution and largest-family review CSV before migrating the production family layer.

### 12. Analyze cross-account propagation

After families exist, derive how each family appears across the manually verified accounts of the same operator:

```bash
uv run creative-research analyze-propagation \
  --members data/06_analytics/creative_family_members.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --out data/06_analytics
```

This writes:

```text
data/06_analytics/
├── family_account_entries.parquet
├── cross_account_propagation.parquet
├── account_propagation_edges.parquet
├── account_sequence_edges.parquet
├── account_role_evidence.parquet
└── propagation_report.json
```

The layer records observable facts such as:

- which account first introduced a family;
- when the same family first appeared on another verified account;
- delay from family origin to that account entry;
- nearest prior observed family member/account;
- which creative dimensions changed or stayed the same;
- relative performance of origin and receiving executions;
- how often each account originates versus imports families.

`account_role_evidence` exposes descriptive signals such as `originator_signal`, `receiver_signal`, and `amplifier_signal`. These are **not** final strategy labels. A later inference layer may use repeated evidence to propose hypotheses such as testing/scaling roles, but it must cite these propagation records and supporting posts.

The nearest-prior account sequence is observational chronology only. It must not be interpreted as proof that one account caused another account to publish.

### 13. Build strategy timeline and change points

The timeline stage summarizes how content mix and operating behavior change across fixed monthly or weekly windows:

```bash
uv run creative-research analyze-timeline \
  --posts data/05_master/posts.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --cadence data/06_analytics/posting_cadence.parquet \
  --family-members data/06_analytics/creative_family_members.parquet \
  --family-entries data/06_analytics/family_account_entries.parquet \
  --frequency month \
  --timezone UTC \
  --out data/06_analytics
```

It writes:

```text
data/06_analytics/
├── strategy_windows.parquet
├── strategy_window_members.parquet
├── strategy_change_points.parquet
└── strategy_timeline_report.json
```

Each window exists at both operator and account scope and stores:

- posting volume / active days / posts per active day;
- slideshow versus video mix;
- product and CTA rates;
- relative performance and cadence medians when available;
- family origins / family entries / imported family entries;
- distributions and top values for hook technique, angle, format, audience, product placement, CTA, and dominant visual type.

Adjacent windows are compared with deterministic distribution distance plus scalar changes. A change point records its score and exact dimensions that shifted. It does **not** assign a semantic label such as “conversion phase” or “testing phase.”

### 14. Discover evidence-backed patterns

After timeline/change points exist:

```bash
uv run creative-research discover-patterns \
  --out data/06_analytics
```

This writes:

```text
data/06_analytics/
├── patterns.parquet
├── pattern_evidence_links.parquet
└── patterns_report.json
```

Current pattern classes include:

1. **creative dimension ↔ performance** — e.g. a hook technique performs above/below the operator's historical account-relative baseline;
2. **cadence after performance** — e.g. high-performing posts are followed by longer/shorter next-post gaps than low performers;
3. **cross-account mutation behavior** — dimensions usually changed or preserved when a family enters another verified account;
4. **family reuse baseline** — multi-post and cross-account family reuse rates;
5. **account flow profile** — medium/high evidence originator/receiver leaning from propagation analytics;
6. **strategy change point** — material adjacent-window shifts with post-level evidence from both windows.

Every pattern stores sample size, support/counter evidence, effect size where meaningful, evidence strength, metrics JSON, and `causal_claim=false`.

`pattern_evidence_links.parquet` links patterns back to stable `post_uid`, `family_id`, and/or `account_id`. These patterns are structured observations — **not yet rules, strategies, lessons, templates, or playbooks**.

### 15. Infer reviewable strategy hypotheses

The next stage promotes multiple evidence patterns into explicit, reviewable hypotheses:

```bash
uv run creative-research infer-strategies \
  --patterns data/06_analytics/patterns.parquet \
  --pattern-evidence data/06_analytics/pattern_evidence_links.parquet \
  --out data/06_analytics
```

This writes:

```text
data/06_analytics/
├── strategy_hypotheses.parquet
├── account_strategy_hypotheses.parquet
├── operator_strategy_hypotheses.parquet
├── strategy_pattern_links.parquet
├── strategy_evidence_links.parquet
└── strategy_hypotheses_report.json
```

Current hypothesis types include:

- **account origin/exploration** — an account repeatedly originates families that propagate elsewhere;
- **account reuse/amplification** — an account repeatedly receives families and may repeat or outperform receiving executions;
- **operator explore→propagate model** — different verified accounts show repeated origin-versus-reuse asymmetry;
- **preserve core / vary execution** — cross-account reuse preserves core concept/structure while changing hook/format/execution;
- **iterative reuse model** — most observed families contain multiple executions rather than one-offs;
- **performance-responsive cadence** — high- and low-performing posts are followed by systematically different posting gaps;
- **temporal strategy shift** — a material measured change between adjacent strategy windows.

Every row remains:

```text
status = hypothesis
causal_claim = false
```

and contains:

- confidence score/band;
- promotion readiness;
- supporting pattern IDs;
- direct counter-pattern IDs when available;
- aggregated counter evidence already carried by supporting patterns;
- alternative explanations;
- sample-size/evidence summaries;
- deterministic inference method.

`strategy_pattern_links.parquet` explains which patterns support or counter each hypothesis. `strategy_evidence_links.parquet` then inherits the underlying post/family/account lineage, so a hypothesis can be traced all the way back to original evidence.

This stage still does **not** create final rules, lessons, templates, or playbooks. Those belong to the next knowledge-promotion layer after human review and/or stronger evidence requirements.

### 16. Promote reviewed/high-confidence evidence into the knowledge bank

Build the typed knowledge layer:

```bash
uv run creative-research promote-knowledge \
  --hypotheses data/06_analytics/strategy_hypotheses.parquet \
  --strategy-evidence data/06_analytics/strategy_evidence_links.parquet \
  --families data/06_analytics/creative_families.parquet \
  --family-members data/06_analytics/creative_family_members.parquet \
  --out data/07_knowledge
```

Optional manual review:

```bash
cp config/knowledge_reviews.example.toml config/knowledge_reviews.toml
# edit local decisions, then:
uv run creative-research promote-knowledge \
  --reviews config/knowledge_reviews.toml
```

The real review file is local/ignored. Review decisions can approve, reject, or hold a hypothesis/family source without editing generated datasets.

The knowledge bank writes both Parquet and JSONL:

```text
data/07_knowledge/
├── strategies.parquet / .jsonl
├── rules.parquet / .jsonl
├── lessons.parquet / .jsonl
├── templates.parquet / .jsonl
├── playbooks.parquet / .jsonl
├── knowledge_catalog.parquet / .jsonl
├── knowledge_source_links.parquet / .jsonl
├── knowledge_evidence_links.parquet / .jsonl
└── knowledge_report.json
```

Every knowledge item has a trust state:

- `promoted` — passed deterministic automatic promotion gates;
- `review_candidate` — useful but should be reviewed before high-impact automation;
- `approved` — explicitly approved in the local review registry;
- `rejected` — explicitly rejected but retained for audit;
- `hold` — deliberately paused pending more evidence.

The bank currently contains:

- **strategies** promoted from sufficiently supported strategy hypotheses;
- **rules** from evidence types that can safely become scoped operating guidance, currently family iteration and preserve-core/vary-execution;
- **lessons** that preserve caveats/alternative explanations without becoming prescriptive;
- **templates** from strong repeated creative families plus cross-account adaptation templates;
- **playbooks** assembled only when multiple operator hypotheses support an explore → propagate → adapt → iterate operating model.

Creative-family templates require repeated executions and sufficient cohesion; singletons are never promoted into templates. Template payloads preserve the core angle, hook formula, creative formula, ordered sequence roles, representative post, family performance, and family IDs.

`knowledge_source_links` maps knowledge items to hypotheses/families. `knowledge_evidence_links` carries lineage further down to pattern/post/family/account evidence, so downstream systems can trace any strategy/rule/template/playbook back toward the source evidence.

### 17. Build the Operator Intelligence Workspace

Build a static research UI from the warehouse/analytics/knowledge outputs already generated:

```bash
uv run creative-research build-intelligence-workspace \
  --out data/07_exports/operator-intelligence

uv run creative-research intelligence \
  --dir data/07_exports/operator-intelligence \
  --open
```

This stage does **not** rerun scraping, Vision, analytics, strategy inference, or knowledge promotion. It only materializes existing tables into browser-friendly JSON and copies a packaged static UI.

Generated workspace:

```text
data/07_exports/operator-intelligence/
├── index.html
├── app.js
├── style.css
├── favicon.svg
├── workspace.json
├── overview.json
├── accounts.json
├── timeline.json
├── families.json
├── patterns.json
├── strategies.json
├── knowledge.json
└── evidence.json
```

The workspace is ordered around the reverse-engineering question:

1. **Overview** — complete operator counts, active knowledge, trust/status audit.
2. **Accounts** — performance baseline, cadence, originator/receiver/amplifier evidence.
3. **Timeline** — historical strategy windows and material change points.
4. **Families** — repeated concepts, members, lifecycle, cross-account propagation.
5. **Patterns** — recurring observations with effect/sample/counter evidence.
6. **Strategies** — hypotheses with confidence, alternative explanations, pattern links.
7. **Knowledge** — strategies/rules/lessons/templates/playbooks with explicit trust status.
8. **Evidence** — canonical posts with creative analysis, relative performance, family membership, sequence, and original URLs.

Drawers preserve drill-down lineage such as:

```text
Knowledge
  -> Strategy hypothesis
  -> Pattern
  -> Family / Post
  -> original source URL
```

The **Operator Intelligence Workspace** and **Reference Workspace** serve different purposes:

- Operator Intelligence Workspace = understand how the operator works and what the system has learned.
- Reference Workspace = inspect/compare/select specific creative executions for downstream Creative Bank handoff.

Neither UI is a new source of truth; both are generated research surfaces over canonical evidence.

### 18. Build or reuse the entire deterministic intelligence pipeline

Once `creative_master` and the verified operator registry exist, the full post-Vision pipeline can be built with one command:

```bash
uv run creative-research intelligence-build \
  --operators config/operators.toml \
  --timezone UTC
```

Optional reviewed knowledge:

```bash
uv run creative-research intelligence-build \
  --operators config/operators.toml \
  --reviews config/knowledge_reviews.toml \
  --timezone UTC
```

The orchestrator intentionally starts at `creative_master`. It never scrapes TikTok and never reruns Vision.

Stages:

```text
warehouse
→ performance
→ cadence
→ families
→ propagation
→ timeline
→ patterns
→ strategies
→ knowledge
→ workspace
→ audit
```

Before executing, every stage is classified:

- `skip` / reported as `reused` — all required outputs exist, parameters match, and outputs are newer than inputs;
- `run` / reported as `rebuilt` — output is missing/stale, an input dependency will change, or parameters changed;
- `blocked` — a required input cannot be found and is not produced by an earlier planned stage.

Rebuild planning follows actual dependencies rather than blindly rerunning every later command. For example, changing the analysis timezone invalidates cadence and timeline-dependent intelligence, but does not rebuild Creative Families merely because cadence appears earlier in the CLI list.

Parameter provenance is also checked from stage reports, including:

- operator registry path for warehouse;
- timezone for cadence/timeline;
- review registry path for knowledge.

Useful controls:

```bash
# show the plan without writing anything
uv run creative-research intelligence-build --dry-run

# rebuild everything deterministic
uv run creative-research intelligence-build --force

# rerun from one stage onward, assuming earlier inputs already exist
uv run creative-research intelligence-build --from-stage patterns

# stop after a stage
uv run creative-research intelligence-build --through-stage knowledge
```

The default pipeline writes:

```text
data/07_exports/operator-intelligence/
├── pipeline_report.json
├── quality_report.json
└── ...workspace files...
```

### 19. Audit quality without rebuilding

Run the audit independently:

```bash
uv run creative-research quality-audit \
  --operators config/operators.toml \
  --timezone UTC
```

If a knowledge-review registry was used for the build, pass the same file:

```bash
uv run creative-research quality-audit \
  --operators config/operators.toml \
  --reviews config/knowledge_reviews.toml
```

The audit checks:

- stage freshness/staleness;
- canonical ID duplicates;
- creative-analysis/performance/cadence/family coverage;
- 100%-expected operator mapping and family membership;
- family → post referential integrity;
- propagation → family/post/account integrity;
- pattern evidence lineage;
- strategy → pattern/evidence lineage;
- knowledge → hypothesis/family/evidence lineage;
- knowledge trust-status counts;
- Operator Intelligence Workspace completeness.

Result status:

```text
pass
warn
fail
```

Hard lineage/integrity problems are failures. Coverage that is materially incomplete is warning/failure depending on severity. Empty pattern/strategy/active-knowledge layers are warnings rather than invented results.

Use `--strict` on `quality-audit` when warnings should also produce a non-zero exit code.

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
-> relative performance + account/operator cadence
-> creative families
-> cross-account propagation + account role evidence
-> strategy timeline + change points
-> evidence patterns
-> strategy hypotheses + counter-evidence
-> knowledge bank: strategies/rules/lessons/templates/playbooks
-> operator intelligence workspace
-> system/reference workspace
```

The operator warehouse is intentionally built before strategy inference. Relative performance, historical cadence, creative families, propagation/account-role evidence, strategy windows/change points, patterns, strategy hypotheses, and the typed evidence-linked knowledge bank are now implemented. Downstream Creative Bank/Creative Director systems can consume the JSONL/Parquet outputs while filtering by scope, confidence, status, validity, and evidence lineage. Those future knowledge assets must retain evidence lineage instead of being unsupported LLM summaries.

Brief/variant production and first-party experiment outcomes remain downstream concerns.

## Test philosophy

Tests are deterministic and do not call TikTok, Apify, or Gemini.

```bash
uv run ruff check .
uv run pytest --cov=creative_research --cov-report=term-missing
```
