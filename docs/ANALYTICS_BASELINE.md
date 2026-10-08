# Historical performance and cadence analytics

These analytics are deterministic transformations of the canonical `posts.parquet` warehouse table.

They do **not** scrape TikTok again, create realtime metric history, or call Gemini/another LLM.

## Performance baseline

Run:

```bash
uv run creative-research analyze-performance \
  data/05_master/posts.parquet \
  --out data/06_analytics
```

The post-level table retains stable `post_uid` and calculates relative performance for:

- views
- likes
- comments
- shares
- saves

For each metric it stores:

- percentile within the account;
- ratio to the account median;
- account sample size;
- percentile within the verified operator;
- ratio to the operator median;
- operator sample size;
- global percentile within the observed dataset.

It also calculates simple engagement-per-view rates when both numerator and views are present.

The account and operator baseline tables keep medians, quartiles, p90/p95, maxima, and observed sample sizes.

### Interpretation

A raw view count is not comparable across accounts with very different normal performance. Relative baselines make statements like these possible:

```text
Post X = 120k views
Account A median = 30k
=> 4x the account median

Post Y = 120k views
Account B median = 500k
=> below normal for Account B
```

These are historical-relative measurements, not realtime velocity.

## Posting cadence

Run:

```bash
uv run creative-research analyze-cadence \
  data/05_master/posts.parquet \
  --out data/06_analytics \
  --timezone Asia/Ho_Chi_Minh
```

Always choose the timezone intentionally when interpreting posting hour and weekday. The source UTC timestamp is preserved.

### Account chronology

For each post the cadence table stores:

- previous/next post on the same account;
- gap from/to the neighboring account post;
- sequence position;
- number of earlier posts in the previous 24 hours / 7 days;
- posting hour, weekday, and post number within the local day.

### Operator chronology

Because verified accounts may belong to the same person/operator, the same post also stores:

- previous/next post across **all** operator accounts;
- which account the previous/next operator post came from;
- operator-level time gaps;
- prior 24h / 7d operator posting density.

This supports later evidence-backed questions such as:

```text
Does Account A usually post before Account B?
How often does the operator switch accounts within a day?
Are high-performing posts followed by longer posting gaps?
Does posting behavior change across strategy periods?
```

The first two are directly observable. Questions connecting performance to later behavior are correlations unless additional causal evidence exists.

## Daily and summary tables

`account_activity_daily.parquet` contains posts/day, active span, content-type counts, and within-day gaps.

`operator_activity_daily.parquet` contains posts/day across all verified accounts, number of active accounts, and account-switch rate.

Account/operator cadence summaries contain historical gap quantiles, posts per active day, and common posting hours/weekdays.

## Evidence boundary

This layer should stay deterministic. It measures what happened in the collected dataset.

Later stages may infer:

- testing versus scaling account roles;
- creative-family propagation;
- strategy shifts;
- rules and playbooks.

Those inferred claims should cite the stable `post_uid` evidence produced here instead of treating an LLM summary as truth.
