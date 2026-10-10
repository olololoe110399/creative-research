# Performance investigation

Start with `data/06_analytics/post_performance.parquet` and
`account_performance_baselines.parquet`; compare operator/global baselines only when
the scope supports them. Read table columns before selecting metrics.

The engine publishes `views_percentile_account`, `views_vs_account_median`,
`views_account_sample_size`, corresponding operator/global fields, and
`save_rate_by_view` / `share_rate_by_view`. Percentiles are fractions, not success
probabilities; a singleton can receive a top percentile without replication.
Ratios with missing/zero denominators stay missing, not zero engagement.

Use `rank-posts` on creative_master for candidate selection; its display/ranking
fields differ from post_performance. Don't transfer column names or scores between
tables. Query the full relevant cohort, then inspect both high and low performers.

Check observation age, publication age, content type, account baseline sample size
and capture completeness. Views and saves can disagree; explain the objective
tradeoff. Never invent attribution, revenue, conversion or an engagement aggregate.
Describe association and propose a controlled test for causal questions.

For full-population comparisons by observed creative dimensions, use
[compare-cohorts](investigation-tools.md) rather than reading the first
100 rows from `query`. Report denominator, eligible metric count, missingness,
selection scope and low-performing counterexamples. The comparison does not
recalculate source metrics or establish treatment effects.
