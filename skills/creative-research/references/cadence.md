# Cadence investigation

Use `data/06_analytics/posting_cadence.parquet`, `account_cadence_summary.parquet`,
`operator_cadence_summary.parquet` and `operator_activity_daily.parquet`.
For changes over time inspect `strategy_windows.parquet` and
`strategy_change_points.parquet`, retaining their scope and window IDs.

Confirm the build's IANA timezone and observed window before interpreting daily/hourly
bins. Compare account-level intervals with operator-level distribution; an operator
can span accounts. Missing capture coverage is not evidence of intentional silence.

Check whether volume, content mix, account mix, post age or incomplete scraping can
explain a timing-performance association. Chronological ordering is not causal proof
of coordination, copying, team staffing or an optimal posting hour.

Suggest a bounded schedule experiment with comparable creatives and a stated review
window. A 30-day calendar is a proposed plan, not a forecast or a recreated private
operator schedule. Do not calculate fresh cadence metrics in language-model prose.
