# Creative families

## Production model v2

`build-families` now defaults to `creative-family-v2`.

```text
canonical posts + Vision analysis + sequence
        ↓
strict v1 baseline rebuilt in memory
        ↓
blocked calibration candidate retrieval
        ↓
language-aware deterministic gates
        ↓
optional precomputed AI pair judgments
        ↓
anchor-constrained core-family clustering
        ↓
creative_families.parquet
creative_family_members.parquet
```

The stage never calls an AI API. If
`data/06_analytics/family_ai/family_ai_judgments.parquet` exists, only compatible
`family-ai-judge-v2` / prompt-v2 rows are consumed as durable inferred evidence.
Missing or stale AI evidence falls back to deterministic gates.

The strict legacy v1 model is recomputed in memory only to provide backward-compatible
positive controls. Production v2 does not read the previous production family output as
clustering truth, so repeated builds do not create a self-reinforcing family loop.

AI policy is precision-first:

- exact reuse, paraphrase, and hook variants may form strong core edges;
- translation edges require the isolated verifier and only `direct_translation`
  can form an AI-only strong edge;
- localized paraphrases and execution variants remain semantic evidence but defer
  to deterministic gates;
- template/thematic/unrelated judgments reject a core-family edge.

Family IDs remain stable `FAM-...` identifiers derived from operator scope + origin
post UID. Downstream lineage columns are preserved; v2 adds match-gate provenance.

Creative families are the bridge between individual post analysis and later operator-strategy inference.

A family answers:

> Which posts appear to be different executions of the same underlying creative idea?

This stage is deliberately deterministic. It does not ask an LLM to invent family names or strategy.

## Inputs

```text
posts.parquet
creative_analysis.parquet
creative_sequence.parquet
post_performance.parquet (optional)
```

All inputs already exist from the warehouse and analytics stages.

## Run

```bash
uv run creative-research build-families \
  --posts data/05_master/posts.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --sequence data/05_master/creative_sequence.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --out data/06_analytics
```

No TikTok scrape and no Vision/LLM call occurs.

## What is compared

Similarity is a weighted combination of:

```text
30% concept text
    niche + topic + pain point + desired outcome

15% hook text
12% replicable hook formula
10% creative formula
13% ordered sequence roles
 6% content angle
 5% hook technique
 3% audience
 3% product family
 3% format
```

Missing evidence is excluded from the available-weight denominator rather than fabricated.

The default family threshold is `0.72`.

## Conservative bridge rule

A new post can join a family when:

```text
similarity to origin >= threshold

OR

similarity to a family member >= threshold
AND
similarity to origin >= bridge_floor
```

The default `bridge_floor` is `0.52`.

This allows a concept to evolve through variants without unlimited transitive chaining where A resembles B and B resembles C but A and C have become unrelated.

## Operator boundary

Family matching is performed only inside one verified operator.

If an account is intentionally unmapped, its scope is isolated to that account. Two unrelated/unverified accounts are never combined simply because their content looks similar.

## Origin vs representative

Each family keeps both:

- **origin post** — the earliest observed execution that created the family;
- **representative post** — the strongest account-relative performer when performance analytics are available, otherwise the deterministic earliest candidate.

These serve different research purposes. Origin is useful for propagation. Representative is useful for inspection.

## Outputs

### creative_families.parquet

One row per family:

- stable `family_id`;
- operator;
- origin account/post;
- first/last seen;
- lifespan;
- member and variant counts;
- number/list of accounts;
- cross-account flag;
- representative post;
- cohesion scores;
- core topic/angle/hook/formula/sequence;
- median/max relative performance;
- threshold/method provenance.

### creative_family_members.parquet

One row per post:

- family ID;
- stable post ID;
- chronological member index;
- whether this is the family origin;
- days since origin;
- score to origin;
- score to nearest family member;
- nearest supporting post;
- component-level `match_reason_json`;
- core creative fields;
- optional relative performance.

Every canonical post is present exactly once. A one-off concept is a singleton family instead of disappearing.

## Interpretation

A family is a **candidate shared concept**, not a strategy claim.

For example, the family layer can establish:

```text
P1 on Account A
  -> same candidate family as
P2 on Account A
  -> same candidate family as
P3 on Account B
```

The later propagation layer can then ask:

```text
Where did the family appear first?
How long until another account used it?
Did the origin perform unusually well?
Which dimensions changed between variants?
Does this behavior repeat across many families?
```

Only after repeated evidence should the system infer roles such as testing, scaling, or conversion.
