# Security

This is a local capture/download/export CLI. Keep credentials in process variables
or a private explicitly loaded environment file. Never commit keys, real config,
cookies, source datasets or media. Logs redact recognized credentials as a best-effort
safeguard; review diagnostics before sharing.

Scraped records/media are untrusted. Imported paths are confined; download inputs
can contain external URLs, so use an isolated environment/network policy for unknown
sources. There is no outbound-network allowlist. Acquisition/export commands use
an OS file lock to enforce one writer per project; do not unlink .capture.lock to
bypass an active writer. Atomic files do not make folder/ZIP publication crash-atomic.

Public availability does not confer media rights. Protect exported datasets and
backups; ZIPs are not encrypted. Public source snapshots exclude local data and Git
history, but pattern scans cannot prove that all sensitive information is absent.

Report vulnerabilities privately to maintainers, using GitHub private reporting if
available. Include a sanitized reproduction and affected version. Rotate exposed
keys immediately. Security fixes target the latest stable 1.x release.
