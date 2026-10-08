# Operator Intelligence Lab

The Operator Intelligence Workspace is a generated browser UI over the existing warehouse, analytics, strategy, and knowledge outputs.

It does not rerun scraping, Vision, analytics, strategy inference, or knowledge promotion.

## Build

```bash
uv run creative-research build-intelligence-workspace \
  --out data/07_exports/operator-intelligence
```

Serve it locally:

```bash
uv run creative-research lab --open
```

## Views

### Overview

Shows operator/account/post/family/pattern/strategy/knowledge counts plus active knowledge and trust-status audit.

### Accounts

Combines each canonical account with:

- historical performance baseline;
- posting cadence summary;
- originator / receiver / amplifier evidence;
- account-scoped strategy hypotheses;
- account-scoped knowledge items.

### Timeline

Shows operator strategy windows and deterministic change points. Highlighted changes are measured distribution shifts, not semantic strategy labels.

### Families

Shows creative-family lifecycle, members, account coverage, cohesion, and cross-account propagation. Family drawers can open canonical post evidence.

### Patterns

Shows structured recurring observations with sample size, effect, support rate, counter evidence, and evidence links.

### Strategies

Shows strategy hypotheses with confidence, promotion readiness, counter evidence, alternative explanations, supporting/counter patterns, and inherited evidence posts.

### Knowledge

Shows strategies, rules, lessons, templates, and playbooks with explicit trust status:

```text
promoted
approved
review_candidate
rejected
hold
```

Rejected and held items remain visible for audit.

### Evidence

Shows canonical posts enriched with:

- original post URL;
- creative analysis;
- account/operator relative performance;
- family membership;
- ordered creative sequence.

## Generated files

```text
workspace.json
overview.json
accounts.json
timeline.json
families.json
patterns.json
strategies.json
knowledge.json
evidence.json
index.html
app.js
style.css
favicon.svg
```

The JSON files are browser-oriented materializations of canonical Parquet/JSONL outputs. They are not new truth sources.

## Lineage drill-down

The workspace supports navigation such as:

```text
Knowledge
  -> Strategy hypothesis
  -> Pattern
  -> Family / Post
  -> original post URL
```

This makes the UI useful for reviewing why a conclusion exists rather than only displaying conclusions.

## Relationship to Reference Workspace

The two workspaces intentionally stay separate.

Operator Intelligence Workspace:

- understand operator behavior;
- inspect strategy evolution;
- review patterns/hypotheses/knowledge;
- audit evidence lineage.

Reference Workspace:

- inspect individual creative executions;
- compare structures;
- select posts for Creative Bank handoff.

Keeping them separate prevents the research UI from becoming overloaded and prevents creative-selection decisions from being confused with operator-level knowledge.

## Packaging

The static intelligence assets are bundled in the Python wheel and checked in CI alongside the existing Reference Workspace assets.


## Product views

The Lab deliberately leads with research value instead of implementation stages:

1. **Research Brief** — operating model, most useful findings, repeated-concept statistics, explicit claim guardrails, top creative families, and account roles.
2. **Account Network** — visual origin → receiver chronology with evidence-gated role labels and strongest cross-account flows.
3. **Creative Library** — repeated concepts shown as visual executions with thumbnails, member/account coverage, chronology, and post-level drill-down.
4. **Research Intelligence** — Observed / Inferred / Unknown, with source links and automatic multilingual family diagnostics; no mandatory Approve/Hold/Reject workflow.
5. **Operator Playbook** — automatic evidence-linked experiments with metrics and stop/recheck conditions. Human hypothesis approval is not a prerequisite.
6. **My Experiments** — first-party selection, progress, observed outcomes and stale-evidence warnings; these actions are not truth certifications.
7. **Advanced** — raw strategy hypotheses, patterns, legacy knowledge and timeline for expert inspection.

**Evidence-to-decision acceptance:** see [RESEARCH_OUTCOME_ACCEPTANCE.md](RESEARCH_OUTCOME_ACCEPTANCE.md) and run creative-research outcome-audit.

Account role denominators count unique originated/imported **families**, not the number of outgoing graph edges. Account and role-hypothesis detail now expose family, original/receiving posts, performance deltas and preserved/changed dimensions. These observations do not establish internal testing intent.

Pipeline stages, schema versions, and generated artifacts remain implementation details rather than the default navigation.

## AI-assisted evidence research (optional)

Open any hypothesis/family evidence item for **AI Investigate** and **AI Challenge**,
or open Operator Playbook for **AI Draft Playbook** and **AI Stress Test**.
AI Investigate uses a **source-specific rubric**. Family review compares
core creative identity, all supplied member hooks, bilingual variants and
sequence structure—not performance, causal distribution or test-to-scale
intent. Hypothesis review separately assesses the stated operator claim.
AI makes proposals only; visually verifying family media remains a human task.

The AI preflight samples supporting and skeptical evidence without calling
the provider; a separate confirmation performs one bounded Gemini call only
when the local Lab has been started with --ai-enabled.

AI findings and experiment proposals link to canonical post/family/pattern/
hypothesis/knowledge IDs. Unknown citations are rejected. Results are saved
outside the static Lab export and remain provisional. The default Lab does not
require or expose human approval of unknowable operator intent. See
[AI_RESEARCH_COPILOT.md](AI_RESEARCH_COPILOT.md).

## Compatibility: historic manual knowledge-review workflow

V3 does **not** show a human Approve/Hold/Reject interface because the
researcher cannot verify internal intent from public posts. Existing local
review registries are retained for audit/compatibility. The old POST /api/review
returns HTTP 410 by default; explicitly pass --enable-legacy-review-actions
only when intentionally using that old workflow.

My Experiments is the supported human decision workflow. It writes a local
operator-scoped plan without changing knowledge or public research evidence.

Use:

```bash
uv run creative-research lab --open --read-only
```

when the research surface should be browse-only.

## Product boundary

The Lab does not invent new findings in the browser. `lab.json` is a productized projection of existing operator/account/family/strategy/knowledge evidence. Statements remain traceable to strategy hypotheses and canonical evidence.


## Durable local media

The Lab does not rely on TikTok CDN URLs as durable evidence media.

TikTok slideshow/cover/video URLs are commonly signed and expire. When archived media exists, generated post previews point to local Lab endpoints:

```text
/api/media/thumbnail/<post_uid>
/api/media/video/<post_uid>
```

The Lab server resolves those endpoints back to the existing archives under `data/02_media/tiktok` and `data/03_video_media`. Videos support HTTP byte ranges so browser playback/seeking works without copying the entire video archive into `data/07_exports`.

Remote CDN URLs are fallback only. Signed URLs whose expiry is already reached (or within the safety margin) are not emitted as preview URLs.

If an archived file and a usable remote fallback are both missing, the UI shows a graceful “Media unavailable” placeholder while retaining the post/evidence metadata.
