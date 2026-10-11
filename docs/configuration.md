# Configuration

Process variables win over an explicitly selected --env-file. No automatic .env
loading or shell expansion occurs. --root overrides CREATIVE_RESEARCH_PROJECT_ROOT;
otherwise paths use the current directory. Global options precede the command.

APIFY_TOKEN is required for live scrape, optional for authenticated media fallback.
APIFY_TOKENS or numbered APIFY_TOKEN_1 variables support fallback token rotation.
Tokens are sent only to HTTPS Apify domains; cross-host redirects drop authorization.

| Variable | Default | Scope |
| --- | --- | --- |
| CREATIVE_RESEARCH_PROJECT_ROOT | Current directory | Root for relative project paths; --root overrides it |
| CREATIVE_RESEARCH_REQUEST_TIMEOUT | 30 | Seconds for Apify SDK requests and direct video HTTP fallback |
| CREATIVE_RESEARCH_SUBPROCESS_TIMEOUT | 900 | Seconds per yt-dlp subprocess |
| CREATIVE_RESEARCH_LOG_LEVEL | INFO | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| CREATIVE_RESEARCH_LOG_FORMAT | text | text/json |

Timeout variables require finite positive seconds. --timeout controls image requests
separately (35 seconds by default); --actor-timeout controls each actor batch (7200
seconds by default). These are individual operation limits, not a total run deadline.
--quiet suppresses human output; --json reports remain visible.

Account files contain one handle or TikTok profile URL per line, with optional
comments/blanks. Invalid paths and empty account lists fail before provider calls.
--max-charge-usd caps EACH actor batch, not the combined cost of a multi-batch run.
Cookies are explicit download options; keep cookie files private.
Run stores acquisition/download settings and normalized handles, but not tokens or
cookie options. Resume needs --env-file and explicit cookie options again when the
remaining stages require them. Completed capture/export validation can be offline.
See [CLI reference](cli-reference.md) for saved defaults and
[troubleshooting](troubleshooting.md) for recovery.
