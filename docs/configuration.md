# Configuration

## Paths and precedence

Global options override corresponding process settings. Process variables override
an explicitly selected `--env-file`; defaults apply last. `.env` never auto-loads.

`--root PATH`, then `CREATIVE_RESEARCH_PROJECT_ROOT`, then cwd selects the project.
Relative data/config/output paths resolve against it; absolute paths stay absolute.
Package resources resolve against the installed package. In-process commands restore
the previous root after execution.

```sh
cp .env.example .env
uv run creative-research --env-file .env doctor --json
uv run creative-research --root /path/to/research --env-file .env status --json
```

The second command loads `.env` under the selected research root. Files accept
literal `KEY=value`, optional `export`, quotes and comments. Quote whitespace/`#`;
no shell expansion, interpolation or execution occurs.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CREATIVE_RESEARCH_PROJECT_ROOT` | cwd | Research root |
| `CREATIVE_RESEARCH_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR or CRITICAL |
| `CREATIVE_RESEARCH_LOG_FORMAT` | `text` | Text/JSON application logs on stderr |
| `CREATIVE_RESEARCH_REQUEST_TIMEOUT` | `30` | Direct video HTTP / Apify medium operations |
| `CREATIVE_RESEARCH_SUBPROCESS_TIMEOUT` | `900` | Whole yt-dlp child process |
| `CREATIVE_RESEARCH_SERVER_REQUEST_TIMEOUT` | `15` | Local HTTP socket reads/writes |
| `CREATIVE_RESEARCH_AI_TIMEOUT` | `90` | Gemini HTTP calls |
| `APIFY_TOKEN` | unset | Explicit capture / media fallback |
| `GEMINI_API_KEY` | unset | Explicit Vision / family judge |
| `NO_COLOR` | unset | Disable automatic ANSI colors |

Timeouts are finite positive seconds, not overall research deadlines. Actor runtime,
upload processing, retries and cost/call caps are separate command options.
Apify uses the 3.2 client API family. Provider model names/availability must be checked
with the provider before spending money; use command-specific `--model` options.
Gemini requires the audited `google-genai>=2.28.0,<3` API contract. `uv.lock` pins
runtime/development dependencies; the build backend is pinned separately in `pyproject.toml`.

## Evidence and state

`config/*.example.*` contains fake schema examples. `operator-setup` records a
researcher-declared grouping; it does not prove ownership or private intent.
Real registries, account lists, environment files and `data/` stay local/ignored.
Knowledge reviews are optional annotations, not a truth gate for automated research.

Creator-team state lives under `data/07_knowledge/operating_state/`, outside generated
`data/07_exports/operator-intelligence/`. Back up evidence and private state together.
Historical outcomes/rights attestations are preserved separately when rebuilding;
they are not silently promoted into validated results. Run one writer per project.
