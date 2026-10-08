# Cross-account propagation and account-role evidence

This stage turns creative families into observed operator behavior.

It answers factual questions such as:

```text
Which account introduced this family first?
When did another verified account first use it?
How long was the delay?
Which creative dimensions changed?
Did the receiving execution outperform the origin relative to its own account?
Does one account repeatedly originate families while another repeatedly imports them?
```

It does not yet answer the causal/strategic question:

> Why did the operator do this?

and it does not assign final roles such as testing, scaling, or conversion.

## Run

```bash
uv run creative-research analyze-propagation \
  --members data/06_analytics/creative_family_members.parquet \
  --analysis data/05_master/creative_analysis.parquet \
  --performance data/06_analytics/post_performance.parquet \
  --out data/06_analytics
```

No TikTok scrape, realtime collection, Vision call, or LLM call occurs.

## family_account_entries.parquet

One row per family/account pair.

It records:

- family and operator;
- account;
- first post observed on that account;
- entry order;
- whether this is the family origin account;
- delay since family origin;
- number of variants on that account;
- first/best/median account-relative performance.

Example:

```text
FAMILY X

1. Account A   day 0    origin
2. Account B   day 2    3 variants
3. Account C   day 5    1 variant
```

This is the cleanest table for family spread across accounts.

## cross_account_propagation.parquet

One row for each non-origin account's first observed family entry.

It keeps:

- origin account/post/time;
- target account/first post/time;
- delay from family origin;
- nearest prior observed family member/account;
- delay from that prior member;
- origin/target relative performance;
- whether target's first post outperformed the origin relative to each account's baseline;
- similarity evidence inherited from the family layer;
- changed/preserved/unknown creative dimensions.

Dimensions compared include:

```text
content type
topic
angle
audience
product family
hook technique
format
hook text
hook formula
creative formula
sequence roles
```

This lets later analysis distinguish:

```text
same concept, same structure, different hook
same concept moved slideshow -> video
same concept preserved angle but changed execution
```

## account_propagation_edges.parquet

Aggregates repeated family origin-to-target observations:

```text
Account A -> Account B
families observed: 17
median delay: 2.4 days
target outperformed origin: 41%
common changed dimensions:
  hook_text: 15
  format: 7
  hook_technique: 6
```

This edge means families originating on A were later observed on B. It is not proof that A directly caused B.

## account_sequence_edges.parquet

This is a different edge.

It uses the nearest prior observed family member before a new account enters the family.

Example:

```text
A origin
  -> B variant
  -> B variant
  -> C first entry
```

For C, the origin edge is:

```text
A -> C
```

but the nearest-prior sequence edge is:

```text
B -> C
```

The table is explicitly labeled `sequence_not_causation`.

## account_role_evidence.parquet

This aggregates evidence per account without assigning a final strategy role.

Key measures:

- `families_participated`
- `origin_families`
- `imported_families`
- `family_origin_rate`
- `imported_family_rate`
- `propagated_origin_families`
- `outbound_propagation_rate`
- `cross_account_participation_rate`
- import/outbound delay
- imported-family repeat rate
- imported first-post outperformance rate

Three descriptive signals are included:

### originator_signal

Weighted from:

```text
family_origin_rate
+
outbound_propagation_rate
```

High values mean the account often introduces families and those families are later observed elsewhere.

### receiver_signal

Based on:

```text
imported_family_rate
```

High values mean the account often participates in families that were observed elsewhere first.

### amplifier_signal

Uses available evidence from:

```text
receiving execution outperforms origin
+
multiple variants produced after import
```

A high value may later support a scaling/amplification hypothesis, but is not itself proof of that role.

## Descriptive profile vs strategy role

The table may label an account:

```text
originator_leaning
receiver_leaning
mixed
insufficient_evidence
```

This is only a compact description of measured family flows.

It must not be renamed to:

```text
testing account
scaling account
conversion account
```

until later inference combines multiple independent patterns and evidence sources.

`evidence_strength` remains separate from direction:

```text
low     < 3 cross-account observations
medium  3-9
high    >= 10
```

So an account can be strongly originator-leaning while still having low evidence strength.

## Evidence lineage

Every propagation event retains stable:

```text
family_id
post_uid
origin_post_uid
target_post_uid
preceding_post_uid
```

A later strategy claim should therefore be traceable:

```text
strategy hypothesis
  -> propagation pattern
  -> account edge
  -> family
  -> posts
  -> original media / Vision evidence
```
