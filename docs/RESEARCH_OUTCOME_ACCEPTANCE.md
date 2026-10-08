# Research Outcome Acceptance — Research Intelligence v3

## North Star

**Creative Research turns public operator evidence into understandable
observations, bounded strategic hypotheses, explicit unknowns and testable
first-party experiments in roughly 5–10 minutes.**

The researcher is not expected to know the studied operator's private
directives. Neither a human approval of an inference nor AI confidence proves
internal test→scale intent. Human actions are reserved for (1) declaring
the account grouping before scraping and (2) deciding what to try on the
researcher's own accounts.

## Setup once, before spending on scraping

    uv run creative-research operator-setup \
      --accounts-file config/target_accounts.txt \
      --operator-id OP-001 --name "Research operator" \
      --confirm-same-operator

    uv run creative-research scrape config/target_accounts.txt \
      --operators config/operators.toml --preflight

A paid scrape fails before invoking Apify if the requested account group
has not been confirmed, mixes operators or includes unregistered accounts.
A user-declared grouping is not external proof of legal ownership.

## Refresh research without collecting data again

For an already-built warehouse, rebuild Lab v3 only:

    uv run creative-research intelligence-build \
      --operators config/operators.toml \
      --from-stage workspace --force

    uv run creative-research quality-audit
    uv run creative-research outcome-audit
    uv run creative-research ai-research-audit --strict
    uv run creative-research lab --open

This does not rescrape, run Vision or change historical family assignments.
Quality reports remain distinct: integrity vs research product vs optional
AI evidence-packet readiness.

## Machine checks

The outcome audit must prove:

- Brief posts/family/reuse counts reconcile with canonical JSON outputs.
- Origin/import account roles use unique family counts, not raw edge counts.
- Every displayed flow traces to an existing family, original/receiving post
  and account, with an original URL.
- Inferred claims link to actual materialized strategy hypotheses.
- Every repeated creative family receives automated consistency diagnostics;
  unresolved multilingual semantics are labelled uncertain rather than
  falsely promoted to fact.
- Research Intelligence includes **Observed**, **Inferred**, and **Unknown**.
- Each suggested experiment has a unique ID, explanatory evidence/method
  basis, and the explicit flag "experiment_not_proven".
- No review approval of operator-internal intent is required for v3 readiness.

In v3, absence of a human-approved knowledge catalog playbook is **not**
a reason to fail or block the display of suggested experiments. Legacy v2
reviewed knowledge remains available separately for historical consumers.

## Audit status

| Status | Meaning |
|---|---|
| fail | Counts, lineage, operator scope, classification, or experiment attribution are broken. |
| ready_for_usability_test | V3 machine contracts pass. No human truth approval required; real usability and semantic quality are not yet certified. |
| conditional_pass | Legacy v2 behavior when no new v3 Research Intelligence is materialized. Regenerate workspace. |

Every run still warns that real browser media playback, Gemini accuracy,
and nontechnical research comprehension are not tested by CI.

## Real operator 5–10 minute test

Give the Lab to someone who has not built the pipeline. Without developer
help, they should be able to:

1. Identify which accounts belong to the user-declared operator.
2. Explain 2 observed counts, 2 bounded inferences and 1 explicitly unknown
   question, **without being asked to Approve hidden operator intent**.
3. Open a cross-account creative family and inspect actual source media,
   structural similarity, chronology and counterexamples.
4. See machine-flagged family uncertainty, particularly multilingual
   candidate matches; not be asked to certify translations they cannot know.
5. Choose at least 2 testable actions from Operator Playbook and add them to
   My Experiments, including metrics and stop/recheck rules.
6. Change experiment progress and log a real result as their own outcome,
   with no automatic claim that the operator's method is proven.

Record time, tasks completed, error cases, media load failures and confusing
language. A green CI run cannot substitute for this final product test.

## Security/trust

The default Lab's historic POST /api/review is retired (HTTP 410).
Legacy compatibility requires an explicit opt-in flag. The normal
human-controlled write is POST /api/experiments, guarded by same-origin,
loopback-only, valid candidate IDs, operator scoping and a private local
storage path. It does not edit canonical evidence, strategy hypotheses
or the knowledge bank.

AI Investigate/Challenge remains optional, source-limited, paid only
after explicit click and subject to validated evidence references.
No Gemini call can independently verify legal operator ownership or
the intent behind public publishing behavior.

See [RESEARCH_INTELLIGENCE_V3.md](RESEARCH_INTELLIGENCE_V3.md) for full
product design and [AI_RESEARCH_COPILOT.md](AI_RESEARCH_COPILOT.md) for
optional AI research details.
