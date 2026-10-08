# Creative family calibration

This diagnostic exists because production family clustering should not be loosened blindly.

The current production model combines free text, hook/formula text, sequence structure, and a small set of categorical fields. On multilingual operator datasets, lexical overlap can be low even when the underlying creative structure is similar.

`calibrate-families` measures that gap without changing production family assignments.

## Run

```bash
uv run creative-research calibrate-families
```

Inputs default to:

```text
data/05_master/posts.parquet
data/05_master/creative_analysis.parquet
data/05_master/creative_sequence.parquet
data/06_analytics/creative_family_members.parquet
```

Outputs:

```text
data/06_analytics/family_calibration/
├── family_calibration_pairs.parquet
├── family_calibration_review.csv
└── family_calibration_report.json
```

No scrape, Vision, LLM, family mutation, or downstream rebuild occurs.

## Two similarity views

### Structure score

Designed to be mostly language-independent. It uses existing fixed Vision taxonomy and ordered sequence evidence:

- content angle;
- value type;
- audience segment;
- hook technique;
- format;
- product family;
- product placement style;
- CTA type;
- dominant visual type;
- ordered sequence roles;
- ordered sequence visual types.

### Semantic-text score

Uses existing Vision descriptive fields:

- niche;
- topic;
- pain point;
- desired outcome;
- hook formula;
- creative formula;
- sequence visual descriptions.

This score is still lexical and may remain language-sensitive. It is deliberately kept separate from structure score so multilingual failure modes stay visible.

### Combined calibration score

For diagnostic ranking only:

```text
72% structure
28% semantic descriptive text
```

This is **not** the production family score and is not automatically used to assign families.

The current production score is also recorded for every screened pair so the report can show cases where language-independent structure is high but the existing family model is low.

## Review CSV

The review CSV keeps a small stratified sample across score bands and separates same-language from cross-language pairs.

Useful columns include:

- left/right post UID;
- left/right account;
- left/right language;
- content angle;
- value type;
- hook technique;
- format;
- topic;
- hook text;
- structure score;
- semantic-text score;
- combined score;
- current production family score;
- whether both posts already belong to the same current family.

This makes threshold calibration a reviewable research task instead of a blind parameter change.

## Report

The JSON report includes:

- all within-operator pair count;
- number screened by structure score;
- number receiving semantic-text scoring;
- candidate counts at multiple score thresholds;
- cross-language candidate counts;
- cross-account candidate counts;
- currently-split high-score pair counts;
- score quantiles;
- current-family recovery counts.

The next production family change should be based on this report plus reviewed candidate examples.

## Why this matters

A broad taxonomy value such as `study_method` is not enough to prove two posts are variants of the same concept.

At the same time, exact lexical similarity is too strict for:

- translations;
- paraphrases;
- hook rewrites;
- cross-account adaptation;
- slideshow ↔ video execution changes.

Calibration therefore separates language-independent structure from lexical evidence before changing production clustering.
