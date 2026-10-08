# Strategy timeline and evidence pattern engine

This layer begins turning the warehouse into reusable intelligence while keeping a strict separation:

```text
facts / derived features
        ↓
patterns
        ↓
later: strategy hypotheses / rules / lessons / templates / playbooks
```

A pattern is not automatically a rule, and a timeline change is not automatically a named strategy.

## Strategy timeline

Run:

```bash
uv run creative-research analyze-timeline \
  --frequency month \
  --timezone UTC \
  --out data/06_analytics
```

Available frequencies:

```text
month
week
```

For weekly windows, weeks run Monday through Sunday.

The analysis timezone affects window boundaries and active-day calculations. Source timestamps remain canonical UTC in the warehouse.

### strategy_windows.parquet

One row per:

```text
scope_type + scope_id + period
```

Scopes:

```text
operator
account
```

A window includes:

- post count;
- active days;
- posts per active day;
- active account count at operator scope;
- slideshow/video mix;
- product rate;
- CTA rate;
- median account/operator-relative performance;
- cadence medians when available;
- family origins;
- family account entries;
- imported family entries;
- distinct families observed;
- full categorical distributions for:
  - hook technique
  - content angle
  - format
  - audience
  - product placement
  - CTA type
  - dominant visual type

Every distribution is stored as JSON plus its top value/share.

### strategy_window_members.parquet

This is the lineage table:

```text
scope
period
post_uid
```

It allows a later change point or strategy claim to show the exact posts from each window.

### strategy_change_points.parquet

Adjacent windows with enough posts are compared.

The score combines:

```text
45% average categorical distribution shift
20% posting-intensity shift
10% content-type shift
10% product-rate shift
10% relative-performance shift
 5% CTA-rate shift
```

Categorical shift uses total variation distance (TVD), where:

```text
0 = same distribution
1 = completely different distribution
```

The default change threshold is `0.24`.

A change-point row stores:

- previous/current period;
- sample size in both windows;
- overall change score;
- whether threshold was crossed;
- changed dimensions;
- per-dimension TVD;
- scalar deltas;
- full previous/current window snapshots.

This says:

> the observed operating/content distribution changed materially here.

It does not say:

> they switched to a conversion strategy because of X.

That semantic interpretation belongs later.

---

# Pattern engine

Run after the upstream analytics:

```bash
uv run creative-research discover-patterns \
  --out data/06_analytics
```

## patterns.parquet

All patterns share a common contract:

```text
pattern_id
pattern_type
scope_type
scope_id
operator_id

title
observation

sample_size
support_count
support_rate
effect_size
evidence_strength

metrics_json
counter_evidence_json

causal_claim = false
```

Stable `PAT-...` IDs are deterministic from pattern type, scope, and key.

## pattern_evidence_links.parquet

A pattern can link to:

```text
post_uid
family_id
account_id
link_role
detail
```

Common link roles include:

```text
population
support
counter
high_performance_cohort
low_performance_cohort
family_population
previous_window
current_window
account_summary
```

This table is critical because downstream knowledge should not lose provenance.

---

# Current pattern classes

## 1. creative_dimension_performance

For each operator, the engine examines values such as:

```text
hook technique
angle
format
product placement
CTA type
visual type
audience
```

A value is emitted only when:

- enough measured posts exist;
- its median account-relative view percentile differs from the operator baseline by at least the configured effect threshold.

Example:

```text
hook_technique=bold_claim
n=24
median percentile=.74
operator baseline=.51
effect=+.23
```

This is an association, not proof the hook caused performance.

## 2. cadence_after_performance

Compares next-post gaps after:

```text
high = account-relative views percentile >= .80
low  = account-relative views percentile <= .20
```

at both same-account and whole-operator chronology.

Example:

```text
high performers -> median next operator post: 11.2h
low performers  -> median next operator post: 4.6h
```

This may later support a hypothesis that the operator lets winners breathe, but the pattern itself remains correlation.

## 3. propagation_dimension_behavior

Across cross-account family entries, each creative dimension is classified as changed or preserved when known.

A pattern is emitted only when one behavior dominates the configured rate (default 70%).

Example:

```text
content_angle preserved: 18/22
hook_text changed: 20/22
format changed: 15/22
```

## 4. family_reuse_baseline

Operator-level baseline:

```text
multi-post family rate
cross-account family rate
median family lifespan
```

This is useful context for later claims about iteration and scaling.

## 5. account_flow_profile

Promotes only medium/high evidence descriptive flow profiles from `account_role_evidence`.

It can say:

```text
originator_leaning
receiver_leaning
mixed
```

It still cannot say:

```text
testing account
scaling account
conversion account
```

## 6. strategy_change_point

Every flagged timeline change becomes a pattern with evidence links to posts in both adjacent windows.

This means a future semantic strategy inference can inspect:

```text
before window posts
after window posts
exact changed dimensions
change score
```

instead of inventing a story from aggregate text.

---

# Evidence strength

Default strength is based on sample size plus effect size when applicable:

```text
high:
  n >= 30
  and effect >= .15 when effect exists

medium:
  n >= 10
  and effect >= .08 when effect exists

low:
  otherwise
```

Some upstream evidence such as account-flow profiles can preserve a stronger explicit evidence-strength assessment when already calculated from repeated propagation.

Low-strength patterns are still useful for exploration but should not automatically become rules.

---

# What comes next

After this layer the repository has:

```text
raw evidence
→ canonical creative data
→ performance/cadence
→ families
→ propagation
→ timeline/change points
→ patterns
```

The next stage may create **strategy hypotheses** by combining independent patterns.

A safe hypothesis contract should look like:

```text
claim
supporting patterns
supporting evidence links
counter patterns/evidence
scope
time period
confidence
alternative explanation
```

Only after that should the system promote durable knowledge into:

```text
rules
lessons
templates
playbooks
```
