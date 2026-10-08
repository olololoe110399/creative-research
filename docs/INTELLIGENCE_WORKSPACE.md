# Operator Intelligence Workspace

The Operator Intelligence Workspace is a generated browser UI over the existing warehouse, analytics, strategy, and knowledge outputs.

It does not rerun scraping, Vision, analytics, strategy inference, or knowledge promotion.

## Build

```bash
uv run creative-research build-intelligence-workspace \
  --out data/07_exports/operator-intelligence
```

Serve it locally:

```bash
uv run creative-research intelligence \
  --dir data/07_exports/operator-intelligence \
  --open
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
