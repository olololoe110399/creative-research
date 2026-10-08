# Operator warehouse foundation

This document describes the first operator-intelligence foundation built on top of the existing Creative Research evidence pipeline.

## Why this exists

A researched account should not be treated as an isolated feed when several accounts have been manually verified as belonging to the same operator. The warehouse adds the missing identity layer:

```text
operator -> account -> post -> creative analysis -> sequence
```

It does not infer strategy yet. The purpose of this stage is to make later strategy work evidence based and reproducible.

## No expensive reruns

`build-warehouse` is an offline backfill stage. It:

- reads an existing validated `creative_master`;
- reads a local manually maintained operator registry;
- reuses existing `analysis_json` and `timeline_json`;
- writes normalized Parquet tables.

It never calls TikTok, Apify, Gemini, or another LLM.

## Registry

Confirm ownership grouping **before scrape**, not as a repeated post-research
approval. The researcher may assert an account set belongs to the same
operator, but this is not independently verifiable proof of legal ownership.
The standard path is:

```bash
uv run creative-research operator-setup \
  --accounts-file config/target_accounts.txt \
  --operator-id OP-001 --name "Research operator" \
  --confirm-same-operator
uv run creative-research scrape config/target_accounts.txt \
  --operators config/operators.toml --preflight
```

For migration from a previously confirmed registry, you can still edit it
directly or copy the tracked example. The old example remains a *fake*
configuration and must not be treated as real verification.

Copy the tracked fake example to a local ignored file:

```bash
cp config/operators.example.toml config/operators.toml
```

Map all manually verified accounts:

```toml
schema_version = "operator-registry-v1"

[[operators]]
operator_id = "OP-001"
name = "operator_001"
verified = true
verification_method = "manual"

[[operators.accounts]]
username = "account_a"
platform = "tiktok"

[[operators.accounts]]
username = "account_b"
platform = "tiktok"
```

An account cannot belong to two operators. By default every account observed in the master must be registered.

## Backfill

```bash
uv run creative-research build-warehouse \
  data/05_master/creative_master.parquet \
  --operators config/operators.toml \
  --out data/05_master
```

Outputs:

- `operators.parquet`: verified operator identity and observed coverage;
- `accounts.parquet`: account-to-operator mapping and optional configured role;
- `posts.parquet`: post facts and performance metrics;
- `creative_analysis.parquet`: normalized post-level creative attributes plus preserved `analysis_json`;
- `creative_sequence.parquet`: one row per slideshow slide or video timeline beat;
- `warehouse_report.json`: deterministic backfill summary.

## Evidence rules

The warehouse separates observed facts from later inference:

1. Raw scrape/media remain immutable evidence.
2. Vision output remains an interpretation layer and is preserved.
3. Warehouse tables normalize existing evidence; they do not invent strategy.
4. Future pattern/strategy/rule/playbook stages should link claims back to canonical `POST-...` identifiers.
