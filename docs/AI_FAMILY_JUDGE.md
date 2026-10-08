# AI family candidate judge

`judge-family-candidates` adds a semantic adjudication layer between deterministic candidate retrieval and family assignment.

It does **not** scrape, rerun Vision, or mutate production families.

## Workflow

```text
calibration candidates
        ↓
budgeted candidate selection
        ↓
Gemini semantic judge
        ↓
cached structured pair judgments
        ↓
family-v2 preview
```

## Dry-run first

```bash
uv run creative-research judge-family-candidates --dry-run
```

Dry-run writes:

```text
data/06_analytics/family_ai/family_ai_plan.json
```

and prints:

- eligible candidate pairs;
- selected pairs;
- estimated input tokens;
- output-token ceiling;
- total-token ceiling;
- estimated USD ceiling;
- hard pair/API-call caps;
- selection reasons.

The default model is `gemini-2.5-flash-lite`.

The built-in standard-price estimate is verified against Google Gemini Developer API pricing on 2026-10-08:

```text
input:  $0.10 / 1M tokens
output: $0.40 / 1M tokens
```

Pricing can change. Override the estimates with:

```bash
--input-usd-per-million <rate>
--output-usd-per-million <rate>
```

## Run judgments

Set the existing Gemini key:

```bash
export GEMINI_API_KEY="..."
uv run creative-research judge-family-candidates
```

Defaults:

```text
max selected pairs              1,000
max API call attempts           1,100
max estimated input/pair        1,800 tokens
max estimated aggregate input   900,000 tokens
max output/pair                   320 tokens
```

The aggregate input estimate controls how many eligible pairs are selected. Retry attempts are separately protected by the hard API-call cap.

## Candidate selection

The judge does not send every calibration pair to AI.

Priority is:

1. pairs already accepted by the deterministic family-v2 preview gate;
2. other pairs with combined score >= 0.74;
3. cross-language pairs with combined >= 0.68 and structure >= 0.90.

Current production-family pairs are excluded because they already act as known positive controls.

## Prompt evidence

AI receives creative evidence only:

- language;
- audience;
- niche/topic;
- content angle/value type;
- pain point/desired outcome;
- hook text/technique/trigger/formula;
- format/narrative structure;
- visual type;
- product/CTA structure;
- creative formula;
- compact ordered sequence roles/visual types/key text.

It does **not** receive views, likes, comments, shares, saves, percentiles, or other performance metrics.

## Structured judgment

Each pair returns:

```text
decision:
  same_core_concept
  different_core_concept
  uncertain

relationship:
  exact_reuse
  translation_adaptation
  paraphrase
  hook_variant
  execution_variant
  thematic_only
  unrelated
  uncertain

core_concept
preserved_dimensions[]
changed_dimensions[]
evidence[]
counter_evidence[]
confidence
reason
```

A shared broad category is explicitly insufficient for `same_core_concept`.

## Cache

Cache identity contains:

```text
pair id
+ evidence hash
+ model
+ prompt version
+ judge schema version
```

Default cache:

```text
data/06_analytics/family_ai/family_ai_cache.jsonl
```

Repeated runs reuse cached judgments unless `--force` is used.

## Outputs

```text
data/06_analytics/family_ai/
├── family_ai_plan.json
├── family_ai_cache.jsonl
├── family_ai_judgments.parquet
├── family_ai_judgments.jsonl
└── family_ai_report.json
```

The report records estimated planning tokens plus actual input/output/total tokens when the Gemini SDK returns usage metadata.

## Preview integration

After judgments exist:

```bash
uv run creative-research preview-families-v2
```

The preview automatically reads:

```text
data/06_analytics/family_ai/family_ai_judgments.parquet
```

Confidence gate defaults to 0.80.

High-confidence AI decisions behave as follows:

```text
same_core_concept
+ allowed same-concept relationship
→ strong AI edge

different_core_concept
or thematic_only / unrelated
→ reject edge

uncertain or confidence < 0.80
→ fall back to deterministic gate
```

This keeps AI as an auditable adjudication layer rather than an unrestricted family generator.
