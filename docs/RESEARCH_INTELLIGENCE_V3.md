# Research Intelligence v3 — No human truth certification

## Product principle

Public evidence can show *what appears in posts* and support bounded hypotheses.
It cannot establish an operator's internal reasons, plans or causal mechanisms.
The researcher has no privileged access to those facts, so there is no
mandatory Approve / Hold / Reject queue for family/strategy conclusions.

The product is:

    Confirm account grouping once → Scrape → Analyze →
      Observed / Inferred / Unknown → Explore alternatives →
      Suggested experiments → My Experiment Plan → Record own results

An experiment is **your decision to test**, never your certification of
another operator's hidden actions or assurance of outcome performance.

## 1. Operator grouping is an input — before scrape

Prepare a local account file (one handle or TikTok URL per line):

    config/target_accounts.txt

Confirm the researcher's explicit grouping:

    uv run creative-research operator-setup \
      --accounts-file config/target_accounts.txt \
      --operator-id OP-001 \
      --name "Research operator 001" \
      --confirm-same-operator

The command creates config/operators.toml, which stays local/gitignored and
contains confirmation method and timestamp. The assertion is not independent
proof of legal ownership.

A free, no-token preflight validates the intended accounts:

    uv run creative-research scrape config/target_accounts.txt \
      --operators config/operators.toml --preflight

Then scrape:

    export APIFY_TOKEN="..."
    uv run creative-research scrape config/target_accounts.txt \
      --operators config/operators.toml \
      --out data/00_raw/apify/OP-001-2026-10

The scraper **fails closed before invoking Apify** when an account is not
in the confirmed registry, is assigned to another operator or the registry
has not been confirmed. Subsets of an operator's declared account set are
allowed; mixed-operator requests must be separated. To modify an existing
registry intentionally use operator-setup --replace (it does not silently
overwrite an earlier grouping).

Existing manually confirmed config/operators.toml files with verified=true
and a verification_method remain usable.

## 2. Machine-owned family identity and cross-language handling

Creative families are algorithmic candidates, not human-certified truth.
The pipeline already represents creative evidence across language-agnostic
semantic dimensions (topic/angle, hook mechanism, creative formula, product
role, sequence). The v3 Lab materializes automatic checks per repeated family:

- member/post links are present and unique;
- anchor match scores and matching lineage are recorded;
- canonical semantic axes agree with the family core when available;
- multilingual families have translation-related gate/candidate evidence;
- structural inconsistency is flagged and kept visible.

States are:

- structurally_consistent_candidate — no current diagnostic issue;
- semantic_uncertain — incomplete/conflicting normalized identity evidence;
- integrity_gap — incomplete or orphan canonical membership.

A **machine QA flag is not proof of a false match**. A source text translated
into a shared language can still describe a distinct creative idea. This
diagnostic stage does not itself retranslate raw videos or silently change
family assignments; it surfaces uncertainties and their exact post IDs.
Use the existing cached family AI judge/calibration pipeline for optional
cross-language semantic adjudication, or AI Investigate on the flagged
family from the Creative Library. No researcher confirmation is required
to generate findings.

## 3. Research Intelligence replaces mandatory Insight Review

The Lab's Research Intelligence tab has three epistemic lanes:

**Observed** — reconciled counts and chronology, such as the share of
repeated creative families and observed cross-account appearances. Counts
are deterministic outputs, not LLM freehand arithmetic.

**Inferred** — algorithm/model hypotheses with claim, scope, cited evidence,
counterevidence, alternatives and confidence. "Origin leaning" is a bounded
interpretation; it is not evidence of a mandated testing account.

**Unknown** — questions public data cannot resolve, including intentional
test-to-scale instructions, why one post followed another, or proven future
performance. An Unknown is not a request for the researcher to guess.

Each lane is available without an approval action. AI Investigate / Challenge
can help analyze a precise materialized source, with a bounded evidence
packet and citation validation. Internal model "approve/hold/reject" machine
states are presented as evidence assessments, not human decisions.
The historical knowledge review registry is retained solely for
compatibility/audit, not as a required North Star workflow.

Normal local Lab sessions now return HTTP 410 to attempts to use the old
POST /api/review; only the explicit compatibility flag
--enable-legacy-review-actions restores historical API writes. This
compatibility API is not displayed in the default UI.

## 4. Operator Playbook: suggest, don't gate

The playbook is generated automatically as **experiment candidates** from
evidence-linked strategies, plus methodological tests where the operator
claim is still unknown. No human review of speculative operator intent is
required to see or use these suggestions. Each entry clearly states:

- what you might test on your own accounts;
- which hypothesis/method inspired it;
- a metric and an explicit stop/recheck rule;
- that neither operator intent nor effectiveness is proven.

Old, manually approved catalog playbooks remain accessible to legacy
clients, but approval of the bundle is NOT a gate for these v3 suggestions.

## 5. My Experiments: first-party decisions and results

From an experiment card click **Add to My Experiment Plan**. This writes
only a local selected experiment, not a human approval of research. The
My Experiments tab lets you change planned/running/evaluated/abandoned
status and record actual metrics plus notes. Results remain *your* first-party
observations; the app does not auto-claim they prove a tactic.

The local store is operator-scoped and outside the public/static Lab root:

    data/07_knowledge/experiment_plans/<sha256-of-operator-id>.json

It is gitignored, written atomically with private file permissions, and
requires same-origin loopback HTTP. A changed candidate snapshot is marked
"needs recheck"; changing its recorded outcome requires reselection, never
a silent reuse of changed research. --read-only Lab mode allows viewing but
denies changes. No provider or Gemini token is needed to maintain this plan.

## Optional AI: deliberately lazy

Opening Research Intelligence does NOT load the Copilot JavaScript and does NOT
request `/api/ai/status`. Each source has a small optional
"Investigate further with AI" action. Only after an explicit click does the
browser check whether local AI was enabled; only when enabled does it download
the AI UI and show an evidence-plan preview. A separate confirmation is
required to spend tokens. No mandatory AI or human truth certification exists.

The old large Copilot card and Human Review queue are not part of v3.

## 6. Rebuild/migrate (no scraping or Vision required)

After checking out the branch:

    uv sync --all-groups
    uv run creative-research intelligence-build \
      --operators config/operators.toml \
      --from-stage workspace --force
    uv run creative-research outcome-audit
    uv run creative-research ai-research-audit --strict
    uv run creative-research lab --open

This refreshes Lab schema v3 from your existing canonical warehouse and
knowledge artifacts. It does not need to rescrape or modify family memberships.

AI is optional and separately enabled:

    export GEMINI_API_KEY="..."
    uv run creative-research lab --open --ai-enabled

All cached AI reports are provenance-versioned and are not promoted into
trusted knowledge. When public data cannot prove something, the product
must communicate uncertainty rather than asking the researcher to approve
the unknown.

## 7. Acceptance gates

Machine acceptance checks counts, family/post lineage, interpretation
references, automatic family QA and experimental source links. A v3
Research Intelligence report no longer requires human approvals for machine
readiness. Real data quality, semantic matching accuracy, media playback,
and whether the nontechnical user can understand and apply results within
5–10 minutes remain separate usability/quality checks.

A green CI result does NOT prove that all multilingual concepts are correctly
matched or that a hypothesis represents the operator's real intentions.
Avoid claiming otherwise.
