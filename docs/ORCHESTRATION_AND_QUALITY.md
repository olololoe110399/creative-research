# Intelligence orchestration and quality audit

These commands make the deterministic post-Vision pipeline repeatable without re-scraping or rerunning Gemini.

## One-command build

```bash
uv run creative-research intelligence-build \
  --operators config/operators.toml \
  --timezone UTC
```

Optional reviewed knowledge:

```bash
uv run creative-research intelligence-build \
  --operators config/operators.toml \
  --reviews config/knowledge_reviews.toml \
  --timezone UTC
```

The orchestrator begins at `data/05_master/creative_master.parquet`. Scraping, media download, and Vision are deliberately outside this command.

## Stage graph

```text
warehouse
  ├─> performance
  ├─> cadence
  └─> families
        ↓
    propagation

performance + cadence + families + propagation
        ↓
     timeline
        ↓
     patterns
        ↓
    strategies
        ↓
     knowledge
        ↓
     workspace
        ↓
       audit
```

Rebuild propagation follows file dependencies, not simply the display order above.

## Freshness rules

A stage is reused when:

- all required outputs exist;
- all required inputs exist;
- the oldest required output is newer than the newest input;
- parameter provenance stored in the stage report matches the requested build.

Currently parameter provenance checks include:

- operator registry path for warehouse;
- timezone for cadence;
- timezone for timeline;
- knowledge review source for knowledge promotion.

Examples:

- edit `creative_master` → warehouse and all dependent intelligence rebuild;
- change timezone → cadence and timeline-dependent stages rebuild, but Creative Families can be reused;
- edit `knowledge_reviews.toml` → knowledge + workspace + audit rebuild;
- delete one workspace asset → workspace + audit rebuild.

## Controls

```bash
# print plan only
uv run creative-research intelligence-build --dry-run

# force all selected deterministic stages
uv run creative-research intelligence-build --force

# begin at an existing intermediate layer
uv run creative-research intelligence-build --from-stage patterns

# stop before later layers
uv run creative-research intelligence-build --through-stage knowledge
```

Valid stages:

```text
warehouse
performance
cadence
families
propagation
timeline
patterns
strategies
knowledge
workspace
audit
```

Starting from a later stage does not fabricate missing inputs. If an excluded upstream artifact is required and missing, the selected stage is blocked.

## Pipeline report

Default:

```text
data/07_exports/operator-intelligence/pipeline_report.json
```

Per stage status:

```text
reused
rebuilt
would_run
```

The report also records timezone, operator registry, review registry, stage range, force/dry-run flags, and output paths.

## Quality audit

Run independently:

```bash
uv run creative-research quality-audit \
  --operators config/operators.toml \
  --timezone UTC
```

Use the same `--reviews` file that was used when building reviewed knowledge.

Default report:

```text
data/07_exports/operator-intelligence/quality_report.json
```

## Audit categories

### Freshness

The audit reuses the same stage specifications as the orchestrator and reports stages that are stale, missing outputs, blocked by missing inputs, or have mismatched parameters.

### Coverage

Coverage includes:

- creative analysis → canonical posts;
- performance → canonical posts;
- cadence → canonical posts;
- creative-family membership → canonical posts;
- post → verified operator mapping.

Coverage below warning/failure thresholds is surfaced explicitly. Missing coverage is never replaced by inferred rows.

### Duplicate IDs

Checks stable IDs in:

- posts;
- accounts;
- operators;
- creative families;
- patterns;
- strategy hypotheses;
- knowledge items.

### Referential integrity

Checks include:

```text
post -> account/operator
analysis/performance/cadence -> post
family member -> family/post
propagation -> family/post/account
pattern evidence -> pattern/post/family/account
strategy links -> strategy/pattern/post/family/account
knowledge sources -> hypothesis/family
knowledge evidence -> knowledge/pattern/post/family/account
```

### Trust status

The report counts knowledge states and warns when the bank has no active `approved` or `promoted` items.

### Workspace completeness

Every required Operator Intelligence Workspace JSON/static file is checked.

## Result status

```text
pass = no audit issues
warn = non-fatal incompleteness or no usable intelligence at some layer
fail = broken integrity, materially insufficient required coverage, stale pipeline, or incomplete workspace
```

`quality-audit --strict` returns non-zero for warnings as well as failures.

## Why the audit is separate

The audit is both the final stage of `intelligence-build` and a standalone command. This allows CI/downstream systems to verify an existing dataset without mutating or rebuilding it.

Quality reports describe the state of the pipeline. They are not an evidence source and must never be used to overwrite canonical data.
