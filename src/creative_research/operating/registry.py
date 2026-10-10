from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from creative_research.identity import normalize_account, stable_account_id

REGISTRY_SCHEMA_VERSION = "operator-registry-v1"


@dataclass(frozen=True, slots=True)
class AccountRegistration:
    username: str
    platform: str = "tiktok"
    role: str | None = None
    notes: str | None = None

    @property
    def key(self) -> str:
        return normalize_account(self.username)

    @property
    def account_id(self) -> str:
        return stable_account_id(self.username)


@dataclass(frozen=True, slots=True)
class OperatorRegistration:
    operator_id: str
    name: str
    verified: bool
    verification_method: str | None
    verified_at: str | None
    notes: str | None
    accounts: tuple[AccountRegistration, ...]


@dataclass(frozen=True, slots=True)
class OperatorRegistry:
    schema_version: str
    operators: tuple[OperatorRegistration, ...]

    def account_map(self) -> dict[str, tuple[OperatorRegistration, AccountRegistration]]:
        result: dict[str, tuple[OperatorRegistration, AccountRegistration]] = {}
        for operator in self.operators:
            for account in operator.accounts:
                if account.key in result:
                    previous = result[account.key][0].operator_id
                    raise ValueError(
                        f"Account @{account.username} belongs to both "
                        f"{previous} and {operator.operator_id}"
                    )
                result[account.key] = (operator, account)
        return result


def _required_text(value: object, label: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"Missing required registry field: {label}")
    return text


def load_operator_registry(path: Path) -> OperatorRegistry:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    schema_version = str(payload.get("schema_version") or REGISTRY_SCHEMA_VERSION)
    if schema_version != REGISTRY_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported operator registry schema {schema_version!r}; "
            f"expected {REGISTRY_SCHEMA_VERSION!r}"
        )

    raw_operators = payload.get("operators")
    if not isinstance(raw_operators, list) or not raw_operators:
        raise ValueError("Operator registry must contain at least one [[operators]] entry")

    seen_operator_ids: set[str] = set()
    operators: list[OperatorRegistration] = []

    for index, raw in enumerate(raw_operators, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"operators[{index}] must be a table")

        operator_id = _required_text(raw.get("operator_id"), f"operators[{index}].operator_id")
        if operator_id in seen_operator_ids:
            raise ValueError(f"Duplicate operator_id: {operator_id}")
        seen_operator_ids.add(operator_id)

        raw_accounts = raw.get("accounts")
        if not isinstance(raw_accounts, list) or not raw_accounts:
            raise ValueError(f"{operator_id} must contain at least one [[operators.accounts]]")

        accounts: list[AccountRegistration] = []
        local_keys: set[str] = set()
        for account_index, account_raw in enumerate(raw_accounts, start=1):
            if not isinstance(account_raw, dict):
                raise ValueError(f"{operator_id}.accounts[{account_index}] must be a table")
            username = _required_text(
                account_raw.get("username"),
                f"{operator_id}.accounts[{account_index}].username",
            )
            account = AccountRegistration(
                username=username,
                platform=str(account_raw.get("platform") or "tiktok").strip(),
                role=(
                    str(account_raw["role"]).strip()
                    if account_raw.get("role") is not None
                    else None
                ),
                notes=(
                    str(account_raw["notes"]).strip()
                    if account_raw.get("notes") is not None
                    else None
                ),
            )
            if account.key in local_keys:
                raise ValueError(f"Duplicate account in {operator_id}: @{username}")
            local_keys.add(account.key)
            accounts.append(account)

        operators.append(
            OperatorRegistration(
                operator_id=operator_id,
                name=_required_text(raw.get("name") or operator_id, f"{operator_id}.name"),
                verified=bool(raw.get("verified", False)),
                verification_method=(
                    str(raw["verification_method"]).strip()
                    if raw.get("verification_method") is not None
                    else None
                ),
                verified_at=(
                    str(raw["verified_at"]).strip() if raw.get("verified_at") is not None else None
                ),
                notes=str(raw["notes"]).strip() if raw.get("notes") is not None else None,
                accounts=tuple(accounts),
            )
        )

    registry = OperatorRegistry(schema_version=schema_version, operators=tuple(operators))
    registry.account_map()
    return registry
