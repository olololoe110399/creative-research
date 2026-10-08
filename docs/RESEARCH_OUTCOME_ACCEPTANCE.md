# Research Outcome Acceptance (v1)

> **Creative Research turns public creator/operator activity into visual, evidence-backed operating intelligence and actionable playbooks.**

The research engine and the final research product have **separate** acceptance gates. Passing data/analytics CI does **not** mean an operator's strategy is proven, a playbook is approved, or a nontechnical user can understand the Lab.

## Rebuild and validate existing evidence

After building the canonical master and verified operator registry, run from the repository root:

    uv run creative-research intelligence-build \
      --operators config/operators.toml \
      --from-stage knowledge

Add --reviews config/knowledge_reviews.toml if a manually reviewed registry exists. The new knowledge schema triggers a one-time rebuild of older outputs and the workspace schema triggers a Lab refresh; stages after knowledge are rebuilt as dependencies change. To explicitly recompute downstream artifacts, use --from-stage knowledge --force. This does not scrape TikTok, rerun Vision, or modify existing analytical family assignments.

Then run:

    uv run creative-research outcome-audit
    uv run creative-research lab --open --read-only

The intelligence build now automatically writes data/07_exports/operator-intelligence/outcome_acceptance_report.json, after the existing quality audit.

**Strict mode:** outcome-audit --strict exits 2 for conditional research readiness, and 1 for broken evidence contracts. Neither mode can certify playback or a user session.

## Machine acceptance contracts

- Research Brief counts reconcile with materialized families/posts.
- Account role denominators count **unique originated/imported families**, not raw propagation events. An origin family reused by five receivers counts once for the originator, but all five receiving executions stay inspectable.
- Every displayed flow joins to a materialized family, original and receiving post, account, and source URL.
- Account/operator role hypotheses expose concrete flow evidence rather than only account-summary links.
- Held/rejected findings cannot appear as usable playbook guidance.
- Algorithmic confidence/automatic promotion are not confused with human approval.
- The measure step is a recommended validation protocol, **not an inference about the operator's internal workflow**.

Older Lab exports must be regenerated after upgrading; the workspace contract is version 2.

## Audit statuses

| Status | Meaning |
|---|---|
| fail | Missing/broken lineage, counts, trust state, or decision mapping. |
| conditional_pass | Research contracts pass, but human-reviewed knowledge or catalog playbook is incomplete. |
| ready_for_usability_test | Research contracts pass, reviewed source steps and a trusted catalog playbook exist; real user testing still outstanding. |

quality_report.json checks the engine's integrity. outcome_acceptance_report.json checks evidence-to-decision presentation. They do not replace each other.

## Human review: required workflow

In Insight Review, for each important operating-model hypothesis:

1. Read the claim and sample denominator; do not treat confidence as review.
2. Inspect supporting/counter patterns and plausible alternative explanations.
3. Click family → original post → receiving post → original TikTok / archived media.
4. Actively inspect losing adaptations, missing posts and counterexamples.
5. Record Approve, Hold or Reject with a substantive note. Approve requires an explicit evidence-inspected confirmation; arbitrary source IDs are rejected by the Lab server.

Review decisions stay in the local, ignored review registry. A hold/reject hides the step's proposed guidance without destroying historical evidence.

## Final 5–10 minute nontechnical acceptance

Ask a user who has never built the pipeline to open the Lab, without coaching, and:

1. Explain the research model and the limits of its claims.
2. Identify origin/receiver-leaning accounts using the correct unique-family denominators.
3. Trace a cross-account family into original and receiving posts; compare preserved and changed execution.
4. Find a counterexample that weakens a tempting narrative.
5. Distinguish reviewed from unreviewed claims.
6. Turn the Operator Playbook into three testable actions with evidence, safeguards and recheck conditions.

Record elapsed time, task completion, where the user needed help and whether archived media actually loaded. **Do not call the product north star complete until this test passes.**

## Known boundaries

- Verified operator-account ownership remains a manual assumption.
- Vision family candidates are not proof of identical intent; sample and review positives and false merges.
- Chronology alone does not prove testing, scaling or causation.
- The provisional Playbook is a research draft for *your experiments*, not an assertion about the operator's documented procedures.
- A research draft is not silently inserted into the knowledge catalog. If there is no trusted playbook, the UI explicitly reports that absence.
- An exported JSON URL for local media does not prove the actual file exists or plays in a different browser/environment.
- The automated audit cannot validate the semantics of every family or human comprehension.
