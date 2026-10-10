# Troubleshooting

## Missing dependencies or files

Run `uv sync --locked --all-groups`, `doctor --json` and `<command> --help`.
Missing optional provider keys are normal for offline work. Check `--root` and
`status --json` before changing paths. Environment files load only with `--env-file`;
process variables win. Configuration errors identify the setting to correct.

## Blocked or interrupted pipeline

Use `intelligence-build --dry-run --json` to inspect dependencies without writes.
Full builds require a validated master and operator registry. `--from-stage` requires
the selected stages' intermediate inputs; it cannot invent missing evidence.

Inspect `<workspace>/pipeline_report.json`. Completed stages and failure causes are
retained. Fix the cause and rerun the same command. A `.pipeline/*.json` running
marker requires replay; removing it can incorrectly reuse partial output. Files are
individually atomic, not one transaction across an entire stage.

## Providers and media

Check grouping, credentials, provider availability, explicit model selection and
budgets. A timed-out request may already have incurred cost. Understand that risk
before retrying. Inspect failure JSONL locally; share only sanitized excerpts.
Vision commands return exit code 1 if any post fails, after retaining diagnostics
and successful checkpoints. Rerun after fixing the cause; use `--force` only when
you deliberately want to spend again. Family judging counts retry attempts toward
call/token caps, falls back to token estimates when usage is absent and still reuses
cached judgments/verifications after a cap is reached. Estimates are not a spending guarantee.
`ffprobe` absence reduces metadata, not rights restrictions. Missing demo media is
expected because synthetic examples contain no real assets.

## Local workspace

Use `--port 0` for an available port. Keep `--host` on loopback; there is no public
authentication. Hidden paths, escaped symlinks, invalid Host/origin and media ranges
are intentionally rejected. Rebuild after asset changes and restart the server.
Shutdown drains in-flight requests within socket timeouts.

## Recovery and safe debugging

`adopt --replace` prints a retained `.backup-<id>` path. Stop writers and inspect both
artifacts before restoring it. Never delete the data tree to repair generated files.
Reference rebuilds retain hidden `.media.backup-*` / `.details.backup-*` directories;
inspect these before restoring or removing them. Failed forced video downloads keep
the last complete video but record failure, not success, in the new manifest/report.
Back up raw evidence, creator-team state, outcomes and rights attestations together.

`--verbose --log-format json` adds application context on stderr; stage prints remain
plain text. Redaction is best-effort. Review reports/logs/screenshots for private
research before sharing. Include version/commit, exact command, exit code and a
synthetic reproduction when reporting a bug.
