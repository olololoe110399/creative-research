"""Validate report structure and cited rows/metrics, not the truth of AI reasoning."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from run_cli import BridgeError, _table, confined, workspace_root

MAX_REPORT_BYTES = 512 * 1024
MAX_TABLE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_TABLE_BYTES = 128 * 1024 * 1024
KINDS = {"research", "strategy", "production"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_report(report: dict[str, Any], root: Path) -> list[str]:
    """Cross-check exact source values. Fail closed; never modify a report or source."""
    errors: list[str] = []
    report_kind = report.get("kind")
    if (
        report.get("schema_version") != "agent-research-v1"
        or not isinstance(report_kind, str)
        or report_kind not in KINDS
    ):
        errors.append(
            "Expected schema_version agent-research-v1 and kind research/strategy/production."
        )
    for field in ("question", "scope", "data_as_of"):
        if not _text(report.get(field)):
            errors.append(f"{field}: provide a nonempty string (use 'unknown' when appropriate).")
    for field in ("unknowns", "proposed_actions"):
        values = report.get(field)
        if not isinstance(values, list) or not values or not all(_text(v) for v in values):
            errors.append(f"{field}: provide a nonempty list of explicit limitations/actions.")
    findings = report.get("findings")
    if not isinstance(findings, list) or not findings or len(findings) > 100:
        return [
            *errors,
            "findings: expected 1–100 findings (including insufficient-evidence findings).",
        ]
    tables: dict[str, Any] = {}
    table_bytes = 0

    def evidence(items: Any, label: str) -> set[tuple[str, str]]:
        nonlocal table_bytes
        identities: set[tuple[str, str]] = set()
        if not isinstance(items, list) or len(items) > 100:
            errors.append(f"{label}: expected a list of at most 100 source citations.")
            return identities
        for index, citation in enumerate(items):
            at = f"{label}[{index}]"
            try:
                if not isinstance(citation, dict):
                    raise BridgeError("citation must be an object")
                path = Path(_table(root, citation["table"]))
                if path.stat().st_size > MAX_TABLE_BYTES:
                    raise BridgeError("source table exceeds the 64 MiB validation limit")
                selectors = citation["row"]
                if (
                    not isinstance(selectors, dict)
                    or not selectors
                    or not all(
                        _text(key) and isinstance(value, (str, int)) and not isinstance(value, bool)
                        for key, value in selectors.items()
                    )
                ):
                    raise BridgeError("row must identify one source row with string/integer keys")
                if not set(selectors) & {
                    "post_uid",
                    "post_id",
                    "family_id",
                    "pattern_id",
                    "hypothesis_id",
                    "account_id",
                    "operator_id",
                }:
                    raise BridgeError("row requires a canonical evidence identifier")
                key = str(path)
                if key not in tables:
                    table_bytes += path.stat().st_size
                    if len(tables) >= 16 or table_bytes > MAX_TOTAL_TABLE_BYTES:
                        raise BridgeError("report exceeds the 16-table / 128 MiB source budget")
                    import pandas as pd

                    if path.suffix == ".parquet":
                        tables[key] = pd.read_parquet(path)
                    elif path.suffix == ".csv":
                        tables[key] = pd.read_csv(path, dtype=object)
                    else:
                        tables[key] = pd.read_json(
                            path, lines=True, dtype=False, precise_float=True
                        )
                matches = tables[key]
                for column, value in selectors.items():
                    if column not in matches:
                        raise BridgeError(f"unknown selector column {column}")
                    matches = matches[matches[column].astype(str) == str(value)]
                if len(matches) != 1:
                    raise BridgeError("citation must resolve to exactly one existing row")
                identities.add((key, json.dumps(selectors, sort_keys=True)))
                metrics = citation.get("metrics", {})
                if not isinstance(metrics, dict):
                    raise BridgeError("metrics must be a map of exact source values")
                for column, expected in metrics.items():
                    if column not in matches:
                        raise BridgeError(f"unknown metric column {column}")
                    actual = matches.iloc[0][column]
                    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                        if not math.isfinite(expected) or float(actual) != expected:
                            raise BridgeError(
                                f"metric {column} differs from source; copy the engine value without rounding/recalculation"
                            )
                    elif expected is None:
                        import pandas as pd

                        if not pd.isna(actual):
                            raise BridgeError(f"metric {column} is not missing in source")
                    elif not isinstance(expected, str) or str(actual) != expected:
                        raise BridgeError(f"metric {column} differs from source")
            except (KeyError, TypeError, ValueError, OSError, ImportError, OverflowError) as exc:
                errors.append(f"{at}: {exc}")
        return identities

    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        label = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{label}: expected an object.")
            continue
        identifier = finding.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen_ids:
            errors.append(f"{label}: id must be a unique nonempty string.")
        else:
            seen_ids.add(identifier)
        for field in ("claim", "confidence_reason", "counterevidence_search"):
            if not _text(finding.get(field)):
                errors.append(f"{label}.{field}: explain explicitly.")
        kind = finding.get("type")
        if not isinstance(kind, str) or kind not in {"observation", "inference", "unknown"}:
            errors.append(f"{label}.type: use observation/inference/unknown.")
        confidence = finding.get("confidence")
        if not isinstance(confidence, str) or confidence not in {"low", "medium", "high"}:
            errors.append(f"{label}.confidence: use low/medium/high, never a success probability.")
        supporting = evidence(finding.get("source_evidence"), label + ".source_evidence")
        evidence(finding.get("counterevidence"), label + ".counterevidence")
        if kind != "unknown" and not supporting:
            errors.append(f"{label}: observations/inferences require verifiable source evidence.")
        if kind == "unknown" and confidence != "low":
            errors.append(f"{label}: unknown findings must retain low confidence.")
        if kind == "inference":
            alternatives = finding.get("alternative_explanations")
            if (
                not isinstance(alternatives, list)
                or not alternatives
                or not all(_text(v) for v in alternatives)
            ):
                errors.append(f"{label}: inference requires alternative_explanations.")
            if confidence == "high" and len(supporting) < 2:
                errors.append(
                    f"{label}: high-confidence inference cannot rest on a singleton citation."
                )
    if report.get("kind") == "production":
        for field in ("original_concept", "rights_review", "measurement_plan"):
            if not _text(report.get(field)):
                errors.append(f"{field}: required for production briefs.")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", required=True)
    parser.add_argument("report", help="JSON sidecar under agent-reports/, not private team state.")
    ns = parser.parse_args(argv)
    try:
        root = workspace_root(ns.root)
        path = confined(root, ns.report)
        if path.relative_to(root).parts[0] != "agent-reports" or path.suffix != ".json":
            raise BridgeError("Reports must be JSON files under agent-reports/ inside --root.")
        if path.stat().st_size > MAX_REPORT_BYTES:
            raise BridgeError("Report exceeds the 512 KiB limit.")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise BridgeError("Report must be a JSON object.")
        errors = validate_report(report, root)
    except (BridgeError, OSError, ValueError) as exc:
        errors = [str(exc)]
    print(json.dumps({"ok": not errors, "errors": errors, "reasoning_verified": False}))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
