# Installation

## Requirements

Use Python 3.11+ and `uv`. CI targets Python 3.11 and 3.13 on Linux and macOS.
Node.js is needed only for contributor UI checks. `yt-dlp` is a Python dependency;
install `ffprobe` separately when you need video metadata.

## From source

```sh
git clone <repository-url>
cd creative-research
uv sync --locked --all-groups
uv run creative-research --version
uv run creative-research doctor --json
uv run creative-research --help
```

Replace `<repository-url>` with the public repository URL. No credentials are needed
for tests, deterministic analysis or the synthetic demo. Doctor reports missing
optional keys without showing values.

```sh
uv run creative-research demo --out ./demo-workspace
uv run creative-research --root ./demo-workspace lab --read-only --open
```

Use a new/empty output directory. Eight fake posts exercise all twelve offline
stages. Missing media and sparse statistical findings are expected; this is not
publishable research. Ctrl+C stops the loopback-only server.

For a real workspace, `creative-research init` creates canonical directories only.
Follow [configuration](configuration.md) and [research workflow](research-workflow.md).
Use `--root /path/to/research` to keep evidence separate from the checkout.
`adopt --mode copy` imports completed artifacts; `--replace` preserves a sibling backup.

## Release artifacts

```sh
make build
make release-check
```

Version 1.0.0 is the initial public stable release under [MIT](../LICENSE).
Build generates wheel/source archives with packaged browser assets. Release checks
install each archive with locked dependencies into separate fresh virtual
environments and exercise every command's help, validation, offline utilities,
pipeline execution and reuse.
They do not publish packages or invoke paid providers.

To install a locally built wheel manually, use a separate environment:

```sh
uv venv /path/to/new-environment
uv pip install --python /path/to/new-environment/bin/python dist/creative_research-1.0.0-py3-none-any.whl
```

The example uses Unix paths; on Windows use the environment's `Scripts/python.exe`.
Only `uv.lock` defines the reproducible contributor/release-check dependency set.
