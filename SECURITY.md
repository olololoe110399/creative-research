# Security

## Intended deployment

This application handles local research and creator-team data. The built-in Lab and
Reference servers are unauthenticated developer servers: bind to loopback only.
Do not tunnel or proxy them onto a public network. HTTP origin/Host checks are
defense-in-depth, not user authentication. Public or multi-tenant deployment needs
a separate authenticated service, authorization, rate limits and a threat review.

## Credentials and evidence

- Keep secrets in process variables, a secret manager, or a private explicitly loaded
  environment file. Never commit `.env`, real configuration, data or media.
- Use minimum provider permissions and explicit cost/call caps. Paid Vision and
  scraping commands are separate from the offline pipeline and UI.
- Application logs redact recognized credentials as a best-effort safeguard. Review
  logs before sharing; do not dump raw provider responses or full environment state.
- Treat scraped text, media and AI output as untrusted. Imported identifiers must
  pass path confinement. Do not reintroduce arbitrary URLs into HTML sinks.
- Protect workspace backups and exported handoffs: private state permissions do not
  encrypt datasets or ZIP files. Set retention policies appropriate to your research.
- Public availability is not copyright clearance. Do not publish source assets until
  rights and editorial checks are satisfied.

## Known limits

There is no multi-process write lock, database transaction, outbound-network allowlist,
formal penetration test or authentication layer. Run one writer per project. Atomic
files and execution markers improve recovery, not distributed consistency. Provider
downloads may access URLs from trusted local inputs; use an isolated environment and
network policy when importing evidence from unknown sources.

## Reporting a vulnerability

Contact the repository maintainers privately. Use GitHub private vulnerability
reporting if it is enabled; otherwise request a private reporting channel without
posting exploit details, secrets or real evidence in a public issue. Include the
affected version/commit, sanitized reproduction, impact and suggested mitigation.
Rotate exposed credentials immediately; do not wait for a code fix.

## Supported versions and publication

Security fixes target the latest stable 1.x release. Built-in servers remain
loopback-only regardless of version. No response-time guarantee or security
certification is implied. Maintainers must enable a private reporting channel before
public publication.

`make snapshot` prepares an allowlisted source ZIP without local data or Git history.
It does not rewrite existing commits or erase previously published information.
Review the archive before making a fresh public repository. Pattern scanning cannot
prove the absence of secrets or personal data; rotate any previously exposed keys.
