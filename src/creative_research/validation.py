from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.constants import (
    ALLOWED_CONTENT_TYPES,
    MASTER_REQUIRED_COLUMNS,
    MASTER_SCHEMA_VERSION,
)


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    level: str = "error"


@dataclass(slots=True)
class ValidationReport:
    ok: bool
    rows: int
    accounts: int
    content_type_counts: dict[str, int]
    issues: list[ValidationIssue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rows": self.rows,
            "accounts": self.accounts,
            "content_type_counts": self.content_type_counts,
            "issues": [
                {"code": issue.code, "message": issue.message, "level": issue.level}
                for issue in self.issues
            ],
        }


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported table format: {path}")


def validate_master(df: pd.DataFrame) -> ValidationReport:
    issues: list[ValidationIssue] = []

    missing = sorted(MASTER_REQUIRED_COLUMNS - set(df.columns))
    if "master_schema_version" in missing:
        issues.append(
            ValidationIssue(
                code="legacy_master_schema",
                message=(
                    "master_schema_version is missing. This master was likely built "
                    "before v0.3.0; rebuild it with the current `creative-research build-master` "
                    "command instead of editing the file in place."
                ),
            )
        )
        missing.remove("master_schema_version")
    if missing:
        issues.append(
            ValidationIssue(
                code="missing_columns",
                message=f"Missing required columns: {', '.join(missing)}",
            )
        )

    for col in ("account", "post_id"):
        if col in df.columns:
            blank = df[col].isna() | df[col].astype(str).str.strip().eq("")
            if blank.any():
                issues.append(
                    ValidationIssue(
                        code=f"blank_{col}",
                        message=f"{int(blank.sum())} rows have blank {col}",
                    )
                )

    if {"account", "post_id"}.issubset(df.columns):
        dup = df.duplicated(["account", "post_id"], keep=False)
        if dup.any():
            issues.append(
                ValidationIssue(
                    code="duplicate_post",
                    message=f"{int(dup.sum())} rows participate in duplicate account+post_id keys",
                )
            )

    if "master_schema_version" in df.columns:
        observed_versions = set(df["master_schema_version"].dropna().astype(str))
        bad_versions = sorted(observed_versions - {MASTER_SCHEMA_VERSION})
        if bad_versions:
            issues.append(
                ValidationIssue(
                    code="invalid_master_schema_version",
                    message=(
                        f"Expected {MASTER_SCHEMA_VERSION}; found: "
                        + ", ".join(bad_versions)
                    ),
                )
            )

    if "content_type" in df.columns:
        observed = set(df["content_type"].dropna().astype(str))
        bad = sorted(observed - ALLOWED_CONTENT_TYPES)
        if bad:
            issues.append(
                ValidationIssue(
                    code="invalid_content_type",
                    message=f"Unexpected content_type values: {', '.join(bad)}",
                )
            )

    for col in ("views", "likes", "comments", "shares", "saves"):
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            negative = vals < 0
            if negative.any():
                issues.append(
                    ValidationIssue(
                        code=f"negative_{col}",
                        message=f"{int(negative.sum())} rows have negative {col}",
                    )
                )

    content_counts: dict[str, int] = {}
    if "content_type" in df.columns:
        content_counts = {
            str(k): int(v) for k, v in df["content_type"].value_counts(dropna=False).items()
        }

    accounts = int(df["account"].nunique()) if "account" in df.columns else 0
    return ValidationReport(
        ok=not any(issue.level == "error" for issue in issues),
        rows=int(len(df)),
        accounts=accounts,
        content_type_counts=content_counts,
        issues=issues,
    )
