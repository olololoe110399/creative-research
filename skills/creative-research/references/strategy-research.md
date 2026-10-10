# Strategy research

Use `data/06_analytics/patterns.parquet`, `pattern_evidence_links.parquet`,
`strategy_hypotheses.parquet`, `strategy_pattern_links.parquet` and
`strategy_evidence_links.parquet`. Engine hypothesis fields include supporting /
counter pattern counts, `confidence_score`, `confidence_band`,
`alternative_explanations_json` and `causal_claim`. Preserve their original labels.

Investigate the user's question independently of the rule engine's preferred
hypothesis: define rival predictions, retrieve relevant rows, search counterexamples,
compare scope/window/cohort and note absent data. A deterministic hypothesis is a
starting point, not a conclusion to paraphrase. Do not rescore engine confidence.

State dispositions: supported association, mixed evidence, unsupported inference or
unknown. Label your qualitative confidence separately from the engine's score.
Singleton patterns, conflicting objective metrics and unsupported private-intent
requests demand a narrower claim or an explicit insufficient-evidence response.

Recommendations must link to findings and specify an experiment, observable signal,
comparison group, review date and stop/adjust rule. A proposed numerical target must
be labeled a proposal; never present it as an observed benchmark.

Use the strategy template. Summarize coverage, contrary evidence, alternative
explanations and unknowns before any 30-day plan. No automatic publishing or team
state changes. Source evidence cannot establish profitability without outcome data.
