# Strategy investigator — agent reasoning over evidence

Use the **same host model**, optionally in three explicit phases, rather than
introducing a separate hidden LLM dependency:

- **Researcher:** formulate multiple falsifiable strategic explanations from
  mechanics, verified descriptive patterns, propagation and timeline.
- **Critic:** seek contrary observations, scope/coverage problems, selection
  bias, operator-mapping uncertainty, alternative mechanisms and missing data.
- **Synthesizer:** compare surviving explanations, their distinct predictions
  and the smallest original experiment able to discriminate between them.

## Baselines and lineage

The old 12-stage pipeline remains available as a deterministic baseline.
When \`strategy_hypotheses.parquet\` exists, inspect selected hypotheses
with \`trace-strategy --hypothesis-id <actual ID>\`: it follows
hypothesis → pattern → post/family/account evidence, with paginated source IDs.
Preserve the engine's confidence and causal-claim fields exactly; **do not
convert them into agent confidence scores**. A pattern echoed in new prose
is not a novel hypothesis.

When operating in \`evidence-only\` mode, these legacy artifacts can be absent
or stale. Do not read them as though they were freshly built. AI must still
research directly from performance, family, propagation and timeline evidence.

## Deliverables

For each candidate strategy:
- a falsifiable claim, scope and source evidence IDs;
- at least one rival explanation and possible counterexample;
- direct observation versus Vision interpretation versus agent inference;
- coverage and correlated-post caveats;
- disposition \`supported_association | mixed | unsupported | unknown\`;
- one original content experiment with a measurable primary signal,
  comparison group, decision date and stopping/adjustment rule.

There is no hidden objective ground truth for an operator's private intention.
Never assert that earlier posting establishes a testing account or later
posting proves scaling. No automatic knowledge promotion, team approval, media
rights assertion, paid providers or publication.
