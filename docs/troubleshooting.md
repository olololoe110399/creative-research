# Troubleshooting

Missing imports: sync locked dependencies and run doctor. Verify --root,
--accounts-file or --input for missing account/post inputs. Preflight does not use
credentials; a live acquisition needs APIFY_TOKEN from process variables or an
explicit --env-file.

Capture/download failures return nonzero and retain successful files. Inspect
pipeline.json, raw/run_info.json, raw/manifest.json and media/download_report.json
inside the run directory. A failed stage may have only its checkpoint error, without
a finished report. Query the state, then resume with credentials supplied again:

```sh
creative-research status --run data/runs/run-001 --json
creative-research --env-file .env run --out data/runs/run-001 --resume --json
```

| Symptom | Recovery |
| --- | --- |
| Actor wait interrupted, saved run_id available | Resume follows the same provider job; it does not start a replacement merely because waiting failed |
| Dataset read failed after actor success | Resume fetches the existing provider dataset again |
| Actor is known FAILED, TIMED-OUT or ABORTED | Explicit resume may start a replacement for that batch; successful batches are reused |
| Actor start rejected with HTTP 401/403 | Correct credentials/account access and resume; the rejected launch can be retried |
| Launch marked launching/launch_unknown without a usable ID | Reconcile provider history and attach the matching ID as shown below |
| Image/video missing, empty or hash/source attestation invalid | Resume verifies the cache and retries those files; unattested files are downloaded again |
| Image URL returns HTTP 200 with HTML/JSON | The response is rejected; another source is tried, otherwise the asset is marked failed |
| yt-dlp cannot start or times out | Direct video URLs are tried; check doctor, cookies and the reported error before resuming |
| Disk full, permission or other file-write failure | Fix the filesystem issue, then resume; completed files remain, and pending image workers are cancelled |
| Pipeline checkpoint has invalid fields/types | Processing stops before provider calls; restore the intact checkpoint or use a new run |
| Successful actor returned provider error rows | Errors stay in the raw archive and capture remains incomplete; a new run is needed to refresh that successful provider snapshot |
| Required media has no usable URL, or source URLs expired | Acquire a new observation, or explicitly accept gaps with --allow-partial; retry cannot create absent source data |
| Completed capture snapshot changed | Pipeline refuses reuse; restore the intact snapshot or use a new run |
| Resume settings/accounts differ | Omit settings to load saved values, supply matching values, or use a new run |
| Published folder intact but ZIP missing | Resume verifies the folder and rebuilds its ZIP |
| Published dataset or existing ZIP is corrupt | Retain it for inspection and export intact sources into a new destination; resume will not overwrite it |

Missing/corrupt batch raw files can be refetched from their saved provider run while
the scrape stage is incomplete, or with standalone scrape --resume. This does not
bypass the completed pipeline capture fingerprint guard. For standalone stages,
repeat scrape with matching settings or run download-media against the same input.
Cookies can help yt-dlp; pass --cookies-from-browser or --cookies-file explicitly on
each invocation that needs them. ffprobe is optional.

Capture rebuilds replace derived post/profile inventories and remove stale derived
files; original batch payloads remain in raw/batches. A retry clears previous
completion before processing. If a checkpoint itself cannot be written, the saved
status describes the last successful write; the CLI still exits with an error.

An incomplete dataset preserves posts and lists missing assets. Integrity success
alone does not prove completeness; check manifest.completion. Strict run can refuse
export for missing required media even when every attempted download succeeded.
Export refuses existing destinations and overlapping source/output paths. Folder/ZIP
publication is not crash-atomic; use pipeline resume to reconcile a recoverable gap.

If a launch outcome is unknown, inspect Apify's run history, then attach the correct
job with --resume --recover-run BATCH=RUN_ID. Do not delete its checkpoint and
blindly relaunch: the earlier job may still be running and charging. SDK automatic
retries are disabled for actor starts. A gap between accepting a provider request
and receiving its ID requires this explicit reconciliation.

For example, after verifying which Apify job belongs to batch 1:

```sh
creative-research --env-file .env run --out data/runs/run-001 \
  --resume --recover-run 1=RUN_ID --json
```

Replace RUN_ID with the verified provider ID. The recovery option attaches that ID;
it does not independently prove that its accounts/settings match the intended batch.

Another writer: stop/wait for the active process in this project. The OS lock is
released on exit, including process death. The retained .capture.lock file itself
does not mean a writer is active; never unlink it to bypass a running writer.
