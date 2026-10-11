# Creative Research

Version **1.0.0** captures public TikTok records, downloads media and exports a
portable dataset for another system to process. `run` coordinates
`scrape → download-media → export-dataset → validate` with durable checkpoints.
Each stage also remains available as a standalone command.

## Quick start

Python 3.11+ is required. Install with uv; ffprobe is optional for video metadata.
Copy `config/target_accounts.example.txt` to a private accounts file and replace
its example handles. Configure APIFY_TOKEN in an explicitly loaded private .env.
Scrape calls Apify and may incur costs; --max-charge-usd caps each batch separately.

```sh
uv sync --locked --all-groups
cp -n config/target_accounts.example.txt config/target_accounts.txt
cp -n .env.example .env
```

Edit the copied account handles and set APIFY_TOKEN in .env before acquisition.
The copy commands preserve existing private files.

```sh
uv run creative-research init
uv run creative-research doctor --json
uv run creative-research scrape --accounts-file config/target_accounts.txt --preflight
uv run creative-research --env-file .env run --accounts-file config/target_accounts.txt --out data/runs/run-001 --max-charge-usd 1 --zip --json
uv run creative-research --env-file .env run --out data/runs/run-001 --resume --json
uv run creative-research status --run data/runs/run-001 --json
```

Each run owns its raw records, media, immutable dataset revisions and pipeline.json.
Resume uses saved settings, skips successful crawl batches, follows persisted Apify
run IDs and verifies cached source fingerprints/SHA-256 before reuse. Failed batches
and missing/corrupt media are retried. An uncertain actor launch is never repeated
automatically; attach its known run ID with --recover-run BATCH=RUN_ID.
The default stops on gaps. --allow-partial permits an inventoried partial handoff,
with status partial and exit 1. Only a complete, validated run returns 0.
See [pipeline contract](docs/pipeline-contract.md) for recovery and publication.
Follow the [capture workflow](docs/capture-workflow.md) for the run directory layout
and the exact dataset/ZIP path to hand off.
Download/export --dry-run performs no writes or network calls. Environment files
are never loaded automatically; global --root resolves relative project paths.

## Dataset handoff

The export includes original source payloads, normalized metadata, downloaded
images/videos, ordered slides, SHA-256 checksums, a CSV convenience table and a
README. Relative paths work after moving or extracting the ZIP on another machine.
Missing/empty assets are inventoried; their posts remain included. The export is
one selected snapshot, not a history of metric observations. Existing exports are
never overwritten. See [dataset contract](docs/dataset-contract.md) and the
[consumer guide](docs/consume-dataset.md) for reading the handoff without this repo.

Other systems own content interpretation, model calls, ranking, analysis and
production workflows. This package has no research engine, model integration or UI.

## Development

```sh
make check
make release-check
make snapshot
```

Checks use mocked providers and synthetic media; they do not certify live TikTok or
Apify behavior. [Architecture](docs/architecture.md), [CLI reference](docs/cli-reference.md),
[configuration](docs/configuration.md), [development](docs/development.md) and
[troubleshooting](docs/troubleshooting.md) cover the supported workflow.
The [documentation index](docs/README.md) separates usage, contracts and maintenance.

[MIT](LICENSE) covers code and documentation, not third-party media. Never commit
keys, datasets or downloaded files. Acquisition/export commands enforce a project
writer lock that releases when the process exits. See
[security](SECURITY.md) and [contributing](CONTRIBUTING.md).
