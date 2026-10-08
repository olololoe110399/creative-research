# AI Research Copilot (opt-in; proposal only)

This adds **AI-assisted evidence investigation** to the Operator Intelligence Lab.
It does not replace deterministic analytics, creative families, hypotheses or
human-approved knowledge.

## Run locally

Build the Lab normally after checking out the feature branch:

    uv sync --all-groups
    uv run creative-research intelligence-build --operators config/operators.toml

Explicitly opt into Gemini model calls with your own API key:

    export GEMINI_API_KEY="..."
    uv run creative-research lab --open --ai-enabled \
      --ai-model gemini-3.5-flash-lite --ai-max-calls 12

The alternative allowlisted model is gemini-3.8-flash. The default limit is
12 model-call **attempts** per server session, including failed attempts.
Do not combine AI-enabled mode with --read-only or a non-loopback host.
Neither the API key nor arbitrary source file paths are sent to the browser.

The provider receives a bounded packet containing public post descriptions,
Vision interpretations, and deterministic observations. Do not use the feature
with data you cannot send to Gemini. Protect local credentials and datasets.

## Research actions

**Insight Review:** Open a review source (hypothesis, family or playbook bundle).

- AI Investigate: interpret what the source supports and does not support,
  inspect counterexamples, and SUGGEST approve / hold / reject.
- AI Challenge: examine evidence against the claim, weaker family matches,
  counterexamples and plausible alternative explanations.

**Operator Playbook:** two related research actions.

- AI Draft Playbook: propose measurable experiments, with stop/recheck
  conditions and validated evidence links. Not a claim about operator intent.
- AI Stress Test: look for failures, coverage gaps, and unsafe generalizations.

Every AI action first shows an evidence-plan preview (free; no provider call).
It lists the source count, selected flow-pair count, approximate input tokens,
output-token ceiling, and model. A separate button authorizes one paid call.
No hidden retries, automatic human approval, or trusted knowledge writes.

## Evidence boundary

The researcher reads six previously materialized Lab outputs:

    lab.json        operator scope, deterministic population totals and trust
    strategies.json hypotheses and their linked patterns, flows and posts
    patterns.json   supporting/counter observations
    families.json   chronology and matched creative concepts
    evidence.json   canonical source posts / URLs / short Vision descriptions
    knowledge.json  knowledge statuses, including held and rejected entries

Evidence is selected deterministically and kept within strict size limits.
Negative receiving-performance results are prioritized alongside stronger
examples; singleton families are included for the playbook when applicable.
This is a targeted **audit sample**, not a statistically representative
sample of the full corpus. Population-wide percentages come from deterministic
Research Brief totals, not LLM counting.

Every model-generated finding or proposed experiment must cite evidence_ref
IDs from the provided packet, such as post:P123 or family:F456. Unknown IDs
are rejected; an output with no independent post/family/pattern reference
fails validation. No arbitrary filesystem, command line, SQL, web browser
or tool execution is available to the model. Public captions and creative
descriptions are explicitly treated as untrusted prompt material.

The output is a research PROPOSAL. It must keep uncertainty and alternatives,
cannot silently promote rejected/held knowledge into guidance, and cannot
write or bypass review decisions.

## Report history and provenance

Validated proposals are stored outside the static Lab document root:

    data/07_knowledge/ai_research/<sha256-prefix>.json

This path is in the repository's gitignored data folder. Reports include the
model, prompt/schema version, timestamp, evidence snapshot SHA-256, source IDs,
coverage, findings and uncertainty. Identical model/evidence/prompt inputs
reuse the saved report (no additional paid attempt).

Use **Saved AI reports** to reopen historical proposals. The server recalculates
the current evidence fingerprint and marks an old report STALE after the
source evidence or reviewed knowledge changes. Reviewing a stale report is
possible, but it should not be used as current proof.

In Insight Review, **Return to Human Review** copies the AI suggestion into
an editable, clearly UNVERIFIED note. The human still inspects source posts,
records an independent rationale, checks the evidence-inspected confirmation,
and explicitly chooses Approve / Hold / Reject. AI never does so automatically.

## Security/cost controls

- Model calls require explicit --ai-enabled and a loopback host.
- Browser POST requires application/json, matching Origin, non-cross-site
  Fetch Metadata, and a bounded request body.
- AI GET/report endpoints also require a loopback Host (DNS-rebinding defense).
- A narrow set of models, max input chars, max output tokens and max calls
  per process prevent uncontrolled spending. Token counts are estimates,
  **not** USD quotes.
- A failed/invalid model output counts as an attempted call; no automatic
  retry can silently repeat charges.
- Every action references a current materialized source, not free-form
  user-entered prompts.
- The private report directory is not served as static web content.

Do not expose --ai-enabled over a LAN/public network. A hosted multi-user
version would first need auth, tenancy and per-user billing budgets.

## What CI can and cannot establish

Offline tests with fake model responses check source scoping, both positive
and negative examples, falsified citations, review boundaries, deterministic
cache invalidation, read-only and same-origin server behavior.

CI cannot prove live Gemini research quality, semantic accuracy of the family
assignments, media playback or improved human decisions. Before merging,
perform a real-operator usability session: compare several AI suggestions with
original post evidence, note false positives and missed counterexamples,
verify the saved report history, and record whether humans make better
approve/hold/reject decisions than without AI.
