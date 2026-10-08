# Evidence-backed strategy inference

This layer is the first place where Creative Research makes explicit **strategy hypotheses**.

The key rule is:

```text
hypothesis != fact
```

A hypothesis is a structured interpretation of multiple deterministic patterns. It keeps support, counter evidence, alternative explanations, confidence, and inherited lineage back to posts/families/accounts.

No LLM is used in this stage.

## Run

```bash
uv run creative-research infer-strategies \
  --patterns data/06_analytics/patterns.parquet \
  --pattern-evidence data/06_analytics/pattern_evidence_links.parquet \
  --out data/06_analytics
```

Outputs:

```text
strategy_hypotheses.parquet
account_strategy_hypotheses.parquet
operator_strategy_hypotheses.parquet
strategy_pattern_links.parquet
strategy_evidence_links.parquet
strategy_hypotheses_report.json
```

## Hypothesis contract

Every hypothesis contains:

```text
hypothesis_id
hypothesis_type
scope_type / scope_id
operator_id / account_id
title / claim
status = hypothesis
causal_claim = false
confidence_score / confidence_band
evidence_strength
promotion_readiness
supporting_patterns_count / counter_patterns_count
independent_pattern_types_count
sample_size_total
supporting_pattern_ids_json / counter_pattern_ids_json
evidence_summary_json / counter_evidence_json
alternative_explanations_json
valid_from / valid_to
inference_method
```

Stable hypothesis IDs start with `STR-`.

## Confidence

Confidence is deterministic and derived from source-pattern quality. Pattern quality combines evidence strength, normalized effect size, support rate, and sample size. Hypothesis confidence then adds a small independent-pattern diversity bonus and subtracts direct counter-pattern penalties.

Confidence remains capped by hypothesis type where interpretation has unavoidable ambiguity. A single account-flow pattern cannot make an account-role hypothesis perfectly certain even when the underlying flow evidence is strong.

```text
high   >= .80
medium >= .60
low    <  .60
```

## Promotion readiness

```text
strong_candidate
review
exploratory
```

A `strong_candidate` currently requires confidence >= .82, no direct counter pattern, and at least two independent pattern types. This prevents one repeated statistic from automatically becoming a durable rule or playbook.

Human review can still reject any hypothesis.

## Account hypotheses

### `account_origin_exploration`

Requires medium/high account-flow evidence with a strong originator signal materially above the receiver signal.

> This account likely acts as a concept-origin / exploration surface.

The wording intentionally says **consistent with testing/exploration**, not that the account is definitely a testing account. Alternative explanations include account age/size/posting volume and incomplete historical coverage.

### `account_reuse_receiver` / `account_reuse_amplification`

Requires receiver signal materially above originator signal. Amplification additionally needs a meaningful upstream amplifier signal.

> This account likely acts as a family reuse / receiving or amplification surface.

Account/audience distribution differences remain alternative explanations.

## Operator hypotheses

### `operator_explore_propagate_model`

Requires at least one medium-confidence origin/exploration account hypothesis and one medium-confidence receiver/amplification account hypothesis. A cross-account family-reuse baseline can strengthen the case.

> The operator likely separates concept origination from downstream reuse/amplification across accounts.

### `preserve_core_vary_execution`

Uses cross-account propagation dimension patterns.

Core dimensions:

```text
topic
content_angle
creative_formula
sequence_roles
```

Execution dimensions:

```text
hook_text
hook_technique
format
content_type
```

Support requires at least one core dimension usually preserved, at least one execution dimension usually changed, and at least two supporting dimension patterns. Opposite dominant behaviors become direct counter patterns.

### `iterative_reuse_model`

Uses `family_reuse_baseline`. Current minimum signal is multi-post-family rate >= 50%. Cross-account reuse and family lifespan remain visible in the evidence summary.

### `performance_responsive_cadence`

Promotes `cadence_after_performance` patterns. Confidence is intentionally capped lower because final historical performance does not prove what metric the operator knew when making the next posting decision.

### `temporal_strategy_shift`

Promotes measured timeline change points. It preserves the previous/current period, change score, exact changed dimensions, and linked posts from both windows. It does not name the semantic strategy.

## Counter evidence

Two forms are preserved:

1. **Direct counter patterns** — for example, a core dimension being usually changed counters a preserve-core hypothesis.
2. **Counter evidence embedded in supporting patterns** — such as opposite-extreme posts, singleton-family counts, single-account-family counts, or non-supporting propagation events.

Direct counter patterns lower confidence. Embedded counter evidence is retained for review even when there is no separate counter pattern.

## Alternative explanations

Each hypothesis type has deterministic alternative explanations. The system must ask both:

> What story fits the data?

and:

> What else could explain the same evidence?

Examples include account age/size, incomplete history, audience differences, preplanned schedules, seasonality, and clustering-threshold effects.

## Evidence lineage

### `strategy_pattern_links.parquet`

```text
STR hypothesis
    ↓ support/counter
PAT pattern
```

### `strategy_evidence_links.parquet`

Inherits every available source-pattern evidence link:

```text
STR hypothesis
    ↓
PAT pattern
    ↓
POST / FAMILY / ACCOUNT evidence
```

A future UI can therefore open a strategy hypothesis, inspect its patterns, then inspect the exact post/family/account evidence and ultimately the Vision/raw media.

## What this layer does not do

It does not create durable knowledge yet. Do not automatically convert a strategy hypothesis into a rule, lesson, template, or playbook.

The next knowledge-promotion stage should set stricter acceptance criteria, preserve scope/time validity, require review where appropriate, and keep both supporting and counter evidence lineage.
