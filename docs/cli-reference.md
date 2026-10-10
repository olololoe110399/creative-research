# CLI reference

```text
creative-research [global options] <command> [command options]
creative-research <command> --help
```

The [command catalog](commands.md) is generated from `cli/registry.py`.
`lab` is the single command for serving the Operator Intelligence Lab.
Command-specific help is authoritative for provider/corpus options.

## Global behavior

- `--root PATH`: resolve project paths consistently without changing cwd.
- `--env-file PATH`: explicitly load literal environment assignments.
- `--verbose` / `-v`: debugging logs and unexpected-error traceback on stderr.
- `--quiet` / `-q`: suppress human stdout and informational application logs.
  Explicit `--json` reports and help remain visible.
- `--log-format text|json`: select application log representation, always stderr.
- `--color auto|always|never`: auto colors only in a TTY, respecting `NO_COLOR`.
- `--help`, `--version` / `-V`: discovery or installed version, without provider calls.

Interactive prompts are restricted to `operator-setup` when requested. Pipelines,
the demo and normal command execution work non-interactively. No spinner/control
sequences are added to redirected output.

## Common workflows

```sh
creative-research init
creative-research doctor --json
creative-research demo --out ./demo-workspace --json
creative-research --root ./demo-workspace lab --read-only --open
creative-research --root ./demo-workspace intelligence-build --dry-run --json
creative-research --root ./demo-workspace intelligence-build --from-stage workspace --force
creative-research --root ./demo-workspace --log-format json --verbose status --json
creative-research adopt --master /path/to/completed-master --mode copy
```

Use `intelligence-build --profile evidence-only` to execute/reuse the six-stage
evidence prefix through `timeline`; default `--profile full` preserves the
12-stage pipeline. Evidence-only reports go to
`data/06_analytics/evidence_pipeline_report.json` rather than the Lab tree.
Do not infer that skipped rule/knowledge/quality stages are fresh. An explicit
`--through-stage` beyond timeline is rejected for evidence-only.

Stage order: warehouse, performance, cadence, families, propagation, timeline,
patterns, strategies, knowledge, workspace, audit, outcome. A dry run reports
blocked inputs but performs no writes. An actual blocked/failed build returns 1
and saves diagnostics; successful completion of the build is distinct from a
quality/outcome report containing warnings or failing acceptance.

`--json` is supported by init, doctor, status, validate, demo and intelligence-build,
not automatically by every stage. Pipeline/demo JSON mode emits one report on
stdout; stage prints and the human plan go to stderr. `--log-format json` formats
application logs only, not every stage progress line. Avoid parsing human
progress text; parse the explicit JSON report and inspect its `status`.

## Exit codes and automation

| Code | Meaning |
| --- | --- |
| `0` | Command completed, help/version shown, or read-only plan produced |
| `1` | Execution/check failure; inspect error and report |
| `2` | Invalid usage, configuration or user path |
| `130` | Interrupted; completed outputs/checkpoints retained |

Strict validators may return 1 for invalid evidence. A dry-run
exit 0 does not mean dependencies exist; its report can have `status: blocked`.
Broken stdout pipes are handled without a traceback.

```sh
creative-research intelligence-build --json >report.json 2>progress.log
```

For a failed/interrupted run, correct the cause and rerun the same command. Running
markers prevent accidentally reusing partial stage outputs. Do not delete private
creator-team state to fix generated output errors.
