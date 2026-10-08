"""Operator/account grouping is a researcher's explicit input, not an AI inference.

The initial declaration happens before any billable scrape. "verified" means
user-confirmed grouping for this research project; not proof of legal ownership.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from creative_research.identity import normalize_account
from creative_research.operator_registry import OperatorRegistration, OperatorRegistry, load_operator_registry


def _accounts_file(path: Path) -> list[str]:
    if not path.is_file():
        raise ValueError(f"Accounts file not found: {path}")
    accounts: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "tiktok.com/@" in line.lower():
            # This is a convenience parser, not an arbitrary URL fetch.
            handle = line.split("tiktok.com/@", 1)[-1].split("?", 1)[0].split("/", 1)[0]
        else:
            handle = line.lstrip("@")
        handle = handle.strip()
        if not handle or any(c.isspace() or c in '#"\\' for c in handle):
            raise ValueError(f"Invalid TikTok handle: {line!r}")
        key = normalize_account(handle)
        if key not in seen:
            seen.add(key)
            accounts.append(handle)
    if not accounts:
        raise ValueError("Accounts file has no accounts.")
    return accounts


def checked_scrape_operator(
    registry: OperatorRegistry, accounts: list[str], *,
    operator_id: str | None = None,
) -> OperatorRegistration:
    """Fail before Apify usage if ownership grouping was not confirmed.

    A partial subset of the declared operator's accounts is supported; mixing
    multiple operators or silently accepting unregistered accounts is not.
    """
    if not accounts:
        raise ValueError("Scrape requires at least one account.")
    mapping = registry.account_map()
    unknown = sorted({
        normalize_account(handle) for handle in accounts
        if normalize_account(handle) not in mapping
    })
    if unknown:
        raise ValueError(
            "Accounts missing from confirmed operator registry: " + ", ".join(unknown)
        )
    group = {
        mapping[normalize_account(handle)][0].operator_id
        for handle in accounts
    }
    if len(group) != 1:
        raise ValueError(
            "A research scrape must target one confirmed operator at a time; "
            "split mixed accounts into separate runs."
        )
    actual_id = next(iter(group))
    if operator_id and operator_id != actual_id:
        raise ValueError(
            f"Selected operator {operator_id!r} does not own requested accounts "
            f"under registry {actual_id!r}."
        )
    operator = next(op for op in registry.operators if op.operator_id == actual_id)
    if not operator.verified:
        raise ValueError(
            f"Operator {actual_id} is not user-confirmed. Use "
            "creative-research operator-setup before scraping."
        )
    if not operator.verification_method:
        raise ValueError(
            f"Operator {actual_id} has no declared confirmation method."
        )
    return operator


def build_operator_registration(
    operator_id: str, name: str, accounts: list[str],
) -> str:
    """Produce an explicit, auditable TOML declaration (never auto-assume)."""
    if not operator_id.strip() or not name.strip():
        raise ValueError("Operator ID and display name are required.")
    if len(accounts) < 1:
        raise ValueError("At least one account is required.")
    timestamp = datetime.now(UTC).isoformat()
    quoted = lambda text: json.dumps(str(text), ensure_ascii=True)
    lines = [
        'schema_version = "operator-registry-v1"',
        "",
        "# Researcher-declared grouping. NOT independent proof of legal ownership.",
        "[[operators]]",
        f"operator_id = {quoted(operator_id.strip())}",
        f"name = {quoted(name.strip())}",
        "verified = true",
        'verification_method = "researcher_confirmed_same_operator_before_scrape"',
        f"verified_at = {quoted(timestamp)}",
        'notes = "Account grouping declared by researcher; identity not independently proven."',
    ]
    for account in accounts:
        lines.extend([
            "",
            "[[operators.accounts]]",
            f"username = {quoted(account)}",
            'platform = "tiktok"',
            'role = "unknown"',
        ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Confirm operator/account grouping once before a paid scrape."
    )
    parser.add_argument("--accounts-file", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", default="config/operators.toml")
    parser.add_argument("--confirm-same-operator", action="store_true",
                        help="Explicitly assert all listed accounts belong to the same operator.")
    parser.add_argument("--replace", action="store_true",
                        help="Explicitly replace an existing local registry.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    accounts = _accounts_file(Path(args.accounts_file).expanduser().resolve())
    if not args.confirm_same_operator:
        raise SystemExit(
            "No registration written: you must explicitly supply "
            "--confirm-same-operator. This assertion is made by the researcher, "
            "not inferred from TikTok or AI."
        )
    content = build_operator_registration(args.operator_id, args.name, accounts)
    destination = Path(args.out).expanduser().resolve()
    if destination.exists() and not args.replace:
        raise SystemExit(
            f"Existing registry protected: {destination}; use --replace intentionally."
        )
    if args.dry_run:
        print(f"Preflight OK: {len(accounts)} accounts; would write {destination}")
        print(content)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Private researcher-controlled local config. Preserve old file on failure.
    temporary = destination.with_suffix(".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    # Self-check generated registry and its exact account membership.
    confirmed = load_operator_registry(destination)
    checked_scrape_operator(confirmed, accounts, operator_id=args.operator_id)
    print(f"Confirmed {len(accounts)} account handles for {args.operator_id}")
    print(f"Local registry: {destination}")
    print("This is a researcher assertion, not independent legal ownership verification.")


if __name__ == "__main__":
    main()
