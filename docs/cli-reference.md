# CLI reference

See the generated [command catalog](commands.md). Commands accept --help without
requests or writes. Use global --root for a project directory and --env-file to
load credentials explicitly; place global options before the command.

## Coordinated pipeline

```sh
creative-research run --accounts-file accounts.txt --out data/runs/run-001 --max-charge-usd 1 --zip --json
creative-research run --out data/runs/run-001 --resume --json
creative-research status --run data/runs/run-001 --json
```

Run saves its accounts/settings, isolates media and exports, checks downloaded
source/hash attestations and validates before reporting completion. Resume can
omit accounts/settings; explicitly different values require a new run. Use
--recover-run BATCH=RUN_ID for an uncertain launch and --allow-partial to permit a
partial export (exit 1). See [pipeline contract](pipeline-contract.md).

Defaults for a new run:

| Option | Default | Scope |
| --- | --- | --- |
| --accounts-file | Required | Normalized and saved as accounts.txt |
| --out | Required | New run directory; existing runs require --resume |
| --batch-size | 4 | Profiles per actor batch |
| --max-posts | 10000 | Maximum requested posts per profile |
| --actor-timeout | 7200 | Seconds per actor batch |
| --max-charge-usd | Unset | Optional USD cap per batch, not a total run budget |
| --oldest-date / --newest-date | Unset | Provider date filters |
| --concurrency | 12 | Concurrent image downloads |
| --timeout | 35 | Seconds per image request |
| --retries | 1 | Image request retries |
| --zip | Off | Also publish and verify the revision ZIP |

On resume, omitted options use saved values. Explicitly different values or accounts
are rejected; use a new run for a different observation. --allow-partial is an
invocation choice and can change on resume. Tokens and cookie options are not saved
in the frozen configuration; reprovide --env-file and any needed cookie options.
Video subprocess/HTTP timeouts use the [runtime settings](configuration.md).

## Standalone stages

For existing inputs or manual orchestration:

```sh
creative-research scrape --accounts-file accounts.txt --out data/raw/run-001 \
  --max-charge-usd 1
creative-research download-media --input data/raw/run-001 --out data/media --dry-run --json
creative-research download-media --input data/raw/run-001 --out data/media --json
creative-research export-dataset --input data/raw/run-001 --media-root data/media \
  --out exports/dataset-001 --require-verified-media --zip
creative-research validate --dataset exports/dataset-001 --json
creative-research status --json
```

Scrape captures records with batch/post/date/comment limits. Media files are
downloaded by download-media into one archive. Scrape has no --json option. Standalone scrape
--resume still requires its account file and matching acquisition settings.

Download supports account subsets, explicit cookies, skipping selected media kinds
and checkpointing. Export reads all image/video files from --media-root.
Download/export --dry-run performs no writes or network calls. Export
--require-verified-media reads download_report.json and only packages files verified
for the selected capture; run always enables this. Standalone export can package
explicit local files without attestations when that flag is omitted.

## Reports and exit codes

Run --json sends one final state to stdout and progress to stderr. Setup errors
before initialization can produce no JSON report. Download --json also separates
progress from its final report; export always prints JSON. Status is a read-only
query: --run reads that pipeline checkpoint; without it, status counts local
workspace files.

| Code | Meaning |
| --- | --- |
| 0 | Command succeeded; for run, a complete validated handoff |
| 1 | Acquisition/download/integrity failure; run also uses this for partial output or an error caught during stage execution |
| 2 | CLI usage or configuration/path errors; for run, setup errors before stage execution |
| 130 | Keyboard interruption; completed files/checkpoints are retained |

Standalone export/validate can succeed with inventoried missing assets; run requires
completeness unless --allow-partial is explicit. Status returns 0 when the checkpoint
can be read, including failed/partial runs; this does not mean the pipeline succeeded.
