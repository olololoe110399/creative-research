# Capture workflow

Install with [installation](installation.md), then copy the account/env templates
as shown in the repository README. Replace the sample handles and set APIFY_TOKEN.
Credentials are loaded explicitly on each invocation.

## Start a run

```sh
uv run creative-research init
uv run creative-research scrape --accounts-file config/target_accounts.txt --preflight
uv run creative-research --env-file .env run \
  --accounts-file config/target_accounts.txt \
  --out data/runs/run-001 --max-charge-usd 1 --zip --json
```

Preflight checks account/path/budget inputs without credentials or provider calls;
it does not confirm account availability. Live run then captures records, downloads
images/videos, exports and validates. The charge cap applies to each actor batch,
not the entire run. Use a new run directory for a new observation.

## Read status and resume

```sh
uv run creative-research status --run data/runs/run-001 --json
uv run creative-research --env-file .env run --out data/runs/run-001 --resume --json
```

Resume uses the saved accounts/settings; omit the original limits or repeat the
same values. Reprovide explicit cookie options if the video download needs them.
Successful capture batches and verified media are reused. See
[troubleshooting](troubleshooting.md) for uncertain launches, expired URLs and
changed/corrupt source snapshots.

Without --json, run prints a status and output path. With --json, stdout contains
one final run-state object, while progress goes to stderr. The state is also saved
in pipeline.json. Errors before the run is initialized can return no JSON report.

```text
data/runs/run-001/
  accounts.txt
  pipeline.json
  raw/
    run_info.json
    manifest.json
    posts/<account>.jsonl
    normalized/posts.jsonl
    profiles/<account>.json
    raw/all_items.jsonl
    raw/errors.jsonl
    raw/batches/
  media/
    <account>/<post_id>/
    <account>/profile/
    download_report.json
  datasets/
    0001/
    0001.zip
```

The inner raw/ directory preserves provider evidence; the outer raw/ directory is
the capture input for download/export. Media attestations and stage reports are
internal recovery files. Dataset revisions are immutable. Revision numbers may
have gaps after failed publication attempts.

## Hand off the result

Use the final report's `dataset` field for the folder and
`stages.validate.result.zip` for the ZIP when --zip was requested. Do not assume
0001 is the current revision after retries. A completed run has status=completed,
complete=true and exit 0. Give the recipient that folder or ZIP plus the
[consumer guide](consume-dataset.md); they do not need the source run or credentials.

--allow-partial explicitly permits an inventoried partial handoff, with
status=partial, complete=false and exit 1. A retry can fill download/failed-batch
gaps and publish a new revision while preserving the earlier handoff. Refreshing
a successful provider snapshot with unavailable accounts requires a new run.

The three standalone stages remain useful for existing inputs; see the
[CLI reference](cli-reference.md). No content interpretation runs between capture
and export. Provider tests use mocks; live acquisition is a separate check.
