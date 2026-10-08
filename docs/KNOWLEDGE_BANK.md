# Knowledge bank

Knowledge Promotion turns reviewed/high-confidence evidence into reusable downstream assets while preserving trust state and lineage.

## Core rule

```text
evidence -> patterns -> hypotheses -> knowledge
```

Knowledge is still scope-bound. It is not universal truth.

## Run

```bash
uv run creative-research promote-knowledge \
  --hypotheses data/06_analytics/strategy_hypotheses.parquet \
  --strategy-evidence data/06_analytics/strategy_evidence_links.parquet \
  --families data/06_analytics/creative_families.parquet \
  --family-members data/06_analytics/creative_family_members.parquet \
  --out data/07_knowledge
```

Optional local review registry:

```bash
cp config/knowledge_reviews.example.toml config/knowledge_reviews.toml
uv run creative-research promote-knowledge --reviews config/knowledge_reviews.toml
```

The real review file is ignored by git.

## Output

Every table is exported as both Parquet and JSONL:

```text
strategies
rules
lessons
templates
playbooks
knowledge_catalog
knowledge_source_links
knowledge_evidence_links
```

## Status

```text
promoted
review_candidate
approved
rejected
hold
```

`promoted` passed automatic evidence gates. `review_candidate` is useful but should be reviewed before high-impact automation. Manual review can explicitly approve/reject/hold a hypothesis or family source.

Rejected and held items remain in the catalog for audit.

## Strategies

Strategy items are promoted from strategy hypotheses above the minimum confidence threshold. They preserve:

- scope (operator/account);
- confidence;
- hypothesis type;
- counter evidence;
- alternative explanations;
- validity period;
- supporting pattern IDs.

Examples include concept-origin/exploration surfaces, reuse/amplification surfaces, explore→propagate operator models, preserve-core/vary-execution behavior, iterative family reuse, cadence associations, and temporal shifts.

## Rules

Rules are intentionally narrower than strategies. Current auto-generated rule types are limited to evidence that can become scoped operating guidance without pretending correlation is causal:

- preserve core concept while varying execution during cross-account adaptation;
- manage recurring concepts as creative families with variants and lifecycle lineage.

Performance-responsive cadence does not become a rule automatically.

## Lessons

Lessons are non-prescriptive learned observations. They retain the original alternatives/counter evidence and are safe for research retrieval even when the item is only a review candidate.

## Templates

Two template classes are produced.

### Creative-family structure templates

Derived from repeated/cohesive families only. Singletons never become templates.

Template payload can include:

```text
core angle
core hook text
core hook formula
core creative formula
ordered sequence roles
origin account
representative post
member / variant / account counts
family cohesion
relative performance
```

Families with the same structural signature are deduplicated and their family IDs are kept as source lineage.

### Cross-account adaptation templates

Derived from the preserve-core/vary-execution hypothesis and contain:

```text
preserve dimensions
vary dimensions
```

These are structural guides, not permission to copy source creative text/media verbatim.

## Playbooks

A playbook is assembled only when multiple operator hypotheses support the same operating model.

The current playbook can combine:

1. concept origin/exploration surfaces;
2. family-level tracking and observed account chronology;
3. **selective cross-account reuse** when the operator-level evidence is strong — without claiming that only winning posts were selected;
4. preserve-core/vary-execution adaptation, only when sufficiently supported;
5. continued family-level iteration, only when sufficiently supported.

An operator explore/propagate hypothesis plus a strong selective-reuse hypothesis
is enough to produce a **review candidate**, even if adaptation and iteration
are not established. The generated playbook explicitly avoids claiming formal
test → scale, causation, or a proven selection rule.

**Playbooks are never auto-promoted.** Unlike narrower descriptive knowledge,
a playbook is a prescriptive artifact. Manual approval of the bundle **and of
every constituent hypothesis** is required for trusted status. A held/rejected
constituent blocks approval even when the bundle itself was approved.
A provisional Playbook view in the Lab is separate from this knowledge catalog:
it is a reviewable application/validation draft, not trusted knowledge.

## Human review workflow

Generate a prioritized source-level review queue:

```bash
uv run creative-research review-knowledge queue
```

This collapses duplicate knowledge representations back to the review source, so one hypothesis that produced both a strategy and lesson is reviewed once.

Review packet and editable decisions are written to:

```text
data/07_knowledge/review/
├── knowledge_review_queue.csv
├── knowledge_review_decisions.csv
├── knowledge_review_packet.md
└── knowledge_review_report.json
```

Apply one decision:

```bash
uv run creative-research review-knowledge decide \
  hypothesis STR-... \
  --decision approve \
  --note "Checked supporting/counter evidence." \
  --reviewed-by researcher
```

Or edit the decisions CSV and apply all non-empty rows:

```bash
uv run creative-research review-knowledge apply \
  --reviewed-by researcher
```

Decisions are stored locally in `config/knowledge_reviews.toml` and remain gitignored.

Allowed decisions:

```text
approve
reject
hold
```

After review, rebuild only the trust-dependent layers:

```bash
uv run creative-research intelligence-build \
  --from-stage knowledge \
  --force \
  --reviews config/knowledge_reviews.toml
```

See `docs/KNOWLEDGE_REVIEW.md` for priority tiers and review discipline.

## Lineage

`knowledge_source_links` maps knowledge to its direct hypothesis/family sources.

`knowledge_evidence_links` inherits lower-level evidence:

```text
knowledge item
  -> hypothesis/family
  -> pattern
  -> post/family/account evidence
  -> Vision/raw media
```

This enables a downstream system to display a rule or playbook and still answer: “Why do we believe this?”

## Consumer guidance

Downstream systems should filter by `knowledge_status`.

For conservative automation:

```text
approved
promoted
```

should be preferred.

`review_candidate` can be used for research/recommendations with visible caveats. `rejected` and `hold` should never be used as active guidance.

## Current boundary

This repository now owns the evidence-derived baseline knowledge bank. First-party experiment results and product-specific decisions still belong downstream and should later feed back as separate evidence rather than overwrite market/operator evidence.
