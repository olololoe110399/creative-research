# Knowledge human review workflow

The knowledge bank is evidence-derived but not automatically human-approved.

This workflow turns review from ad-hoc TOML editing into a source-level review queue.

## Why source-level review

One strategy hypothesis can produce multiple knowledge items, for example:

```text
one hypothesis
  -> strategy
  -> lesson
```

Reviewing those two rows separately would duplicate work and could create inconsistent trust states.

The review queue therefore collapses knowledge items to the source that actually receives the decision:

```text
hypothesis:<STR-...>
family:<FAM-...>
playbook_sources:<bundle-key>
```

A single source decision is then applied consistently to every knowledge item derived from that source.

## 1. Build the queue

```bash
uv run creative-research review-knowledge queue
```

Outputs:

```text
data/07_knowledge/review/
├── knowledge_review_queue.csv
├── knowledge_review_queue.jsonl
├── knowledge_review_decisions.csv
├── knowledge_review_packet.md
└── knowledge_review_report.json
```

The queue is rebuilt in memory from current strategy/family evidence and the same knowledge-promotion logic used by production. It does not mutate the production knowledge bank.

By default, already manually reviewed sources are excluded.

Use:

```bash
uv run creative-research review-knowledge queue --include-reviewed
```

for a complete audit view.

## Priority tiers

The queue prioritizes decisions that change the operating model before lower-value temporal review.

### Tier 1

- auto-promoted items that still deserve human audit;
- operator explore/propagate models;
- selective cross-account reuse models;
- account origin/exploration hypotheses;
- account receiver/amplification hypotheses.

### Tier 2

- preserve-core/vary-execution behavior;
- iteration/cadence hypotheses;
- creative-family templates;
- adaptation templates/playbooks;
- other reusable knowledge candidates.

### Tier 3

- temporal strategy shifts.

Temporal shifts are not discarded. They are simply reviewed after the higher-leverage operating-model evidence.

## 2. Review the packet

Open:

```text
data/07_knowledge/review/knowledge_review_packet.md
```

Each source shows:

- priority;
- source ID;
- confidence;
- generated knowledge types/subtypes;
- evidence-link/post/family/pattern counts;
- the current statement;
- a source-specific review focus.

Review decisions remain:

```text
approve
reject
hold
```

Interpretation:

- approve — human-validated for the recorded scope;
- reject — evidence/claim is not trustworthy enough;
- hold — potentially useful but needs more evidence/inspection.

## 3A. Review one source

```bash
uv run creative-research review-knowledge decide \
  hypothesis STR-EXAMPLE \
  --decision approve \
  --note "Checked supporting and counter evidence." \
  --reviewed-by researcher
```

This creates or updates:

```text
config/knowledge_reviews.toml
```

The real review file is gitignored.

## 3B. Review in bulk

Edit:

```text
data/07_knowledge/review/knowledge_review_decisions.csv
```

Fill only the rows you have actually reviewed:

```text
decision = approve | reject | hold
note
reviewed_by
reviewed_at (optional)
```

Then apply all non-empty decisions:

```bash
uv run creative-research review-knowledge apply \
  --reviewed-by researcher
```

Blank decision rows are ignored.

Existing decisions are preserved unless the same source is reviewed again, in which case the newer decision replaces it.

## 4. Rebuild the trust layer

After writing review decisions:

```bash
uv run creative-research intelligence-build \
  --from-stage knowledge \
  --force \
  --reviews config/knowledge_reviews.toml
```

This rebuilds:

```text
knowledge
-> workspace
-> quality audit
```

It does not rerun family inference, scraping, Vision, or Gemini.

## Trust states after rebuild

```text
promoted
review_candidate
approved
rejected
hold
```

Manual review overrides the automatic trust state for the reviewed source.

Rejected/held knowledge remains in the catalog for audit but should not be used as active guidance.

## Review discipline

Approval means:

> the item is supported enough to use inside its recorded operator/account/time scope.

Approval does not mean:

- universal truth;
- causal proof;
- permission to generalize to other operators;
- permission to automate a high-impact decision without further validation.

Keep notes concrete. Good notes usually mention the evidence checked, the key caveat, or why the source was rejected/held.
