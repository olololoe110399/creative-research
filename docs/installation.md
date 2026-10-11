# Installation

Python 3.11+ is required. From source run `uv sync --locked --all-groups`; for a
runtime-only checkout use `uv sync --locked --no-dev`. A built wheel can be installed
with pip. Runtime dependencies are Apify client, httpx and yt-dlp. ffprobe is optional.

```sh
uv run creative-research --version
uv run creative-research doctor --json
uv run creative-research --help
```

APIFY_TOKEN is required for acquisition and optional for authenticated media URLs.
Export and validation are offline. Use [configuration](configuration.md) for
explicit environment loading.
