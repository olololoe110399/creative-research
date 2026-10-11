# Capture pipeline contract

`run` coordinates scrape, download, export and validate. No model, analytics,
production, scheduler, database or browser service participates.

```sh
creative-research run --accounts-file accounts.txt --out data/runs/run-001 --max-charge-usd 1 --zip --json
creative-research run --out data/runs/run-001 --resume --json
creative-research status --run data/runs/run-001 --json
```

Each run owns accounts.txt, raw/, media/, datasets/0001 and pipeline.json. Later
publications use 0002, etc., preserving existing handoffs. Store runs under ignored
data/; checkpoints, media and datasets are private local artifacts.

pipeline.json uses creative-capture-run-v1, a stable run_id, frozen acquisition
settings/accounts, stage attempts/timestamps/results and a final status. Stage
states are pending, running, completed, partial, failed or interrupted. Final
completed requires successful capture, no download failures, no missing required
media and a valid dataset/optional ZIP. Exit codes: completed 0, partial/failed 1,
setup/usage errors before stage execution 2, interrupted 130. Errors caught during
pipeline execution become failed state with exit 1, including invalid stage input.
Status queries return 0 when readable, irrespective of the saved run status.

Resume loads saved settings, rejects explicit changes and verifies the completed
capture snapshot. Changed completed capture inputs are rejected; resume does not
automatically replace them. Tokens and cookie options are not frozen into the saved
configuration; supply them again if needed. Successful batches reuse checksummed
raw items. While the scrape stage is incomplete, missing/corrupt batch files or a
failed dataset read are recovered from the existing provider run. Standalone scrape
--resume supports the same batch recovery with matching inputs/settings.
The actor start response is checkpointed before waiting. Resume waits on that ID;
only a known failed/aborted/timed-out job can be replaced with a new paid job.
Starts use no automatic SDK retries. A lost start response is recorded as unknown:
resume will not launch that batch again without reconciliation. Supply a known
matching Apify job using --recover-run BATCH=RUN_ID. Run IDs must belong to the
intended batch; provider/account correctness still requires live verification.
An explicit HTTP 401/403 rejection during actor start is recorded as launch_rejected;
after correcting credentials/access, resume can retry that rejected launch. Server
errors and transport failures retain the uncertain-launch guard.

Download checks per-file source fingerprints, SHA-256 and byte counts. An
interrupted write never produces a trusted cache entry. Successful files survive
failure and are reused after verification; absent/corrupt/source-changed files are
retried. The aggregate report binds the current capture to its verified asset
inventory. Export only includes that inventory; stale retained files are excluded.
On an image worker exception, pending peers are cancelled and completed results
are checkpointed before the exception propagates. Filesystem failures are fatal;
fix space/permissions before resuming. Invalid checkpoint structures are rejected
before acquisition. Retrying clears prior completion/results for the active attempt.

Without --allow-partial, capture/download gaps stop downstream publication. Missing
required media with no usable URL also stops export. --allow-partial preserves
source posts, inventories gaps and permits a valid partial dataset with exit 1.
Retrying a partial run can publish a new full revision. Integrity failure is always
fatal, even with --allow-partial. Validity alone does not mean capture is complete.
Provider error records from a succeeded actor remain in raw/all_items.jsonl and
raw/errors.jsonl, are counted in capture provenance and prevent complete status.
They are not exported as posts without valid post records. Successful provider
snapshots are reused on resume; acquire a new run to refresh unavailable accounts
or expired source URLs. Capture completion means the requested sample/filters ran
without recorded failures; it does not prove exhaustive account history or source
metadata accuracy. See the [dataset contract](dataset-contract.md) for required
media rules and the [consumer guide](consume-dataset.md) for completeness checks.

Export validates its staged folder before publishing. If interrupted after folder
publication, resume verifies the manifest's input lineage and all checksums before
reusing it. A missing ZIP is rebuilt; an existing ZIP is checked against the folder.
Corrupt published data is rejected and retained for inspection, never overwritten.
Only after final validation does the pipeline report completion.

Capture/download/export entrypoints use a nonblocking OS file lock per project.
Nested calls in the same thread share ownership; other processes/threads fail
before acquisition writes or provider calls. OS exit releases ownership. Never
delete .capture.lock to bypass an active writer. Atomic file checkpoints and
recovery handle process interruption; folder/ZIP publication is not a single
crash-atomic filesystem transaction. All automated tests use mocked providers;
live provider quality, large-scale performance and power-loss behavior are separate
verification boundaries.
