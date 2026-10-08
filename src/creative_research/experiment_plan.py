"""Local first-party experiment decisions, separate from observed operator truth.

Selecting an experiment means "I want to test this", never "the operator
really did this" or "the tactic is proven to work".
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ExperimentPlanError(ValueError):
    pass


class ExperimentPlanStore:
    MAX_NOTES = 2000
    ACTIONS = frozenset({"add", "remove", "progress"})
    STATES = frozenset({"planned", "running", "evaluated", "abandoned"})

    def __init__(self, workspace: Path, *, directory: Path | None = None) -> None:
        self.workspace = workspace.resolve()
        self.directory = (
            directory or self.workspace.parent.parent / "07_knowledge" / "experiment_plans"
        ).resolve()
        self.lock = threading.Lock()

    def _candidate_map(self) -> tuple[str, dict[str, dict[str, Any]]]:
        try:
            lab = json.loads((self.workspace / "lab.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExperimentPlanError("research_workspace_unavailable") from exc
        operator_id = str(
            lab.get("research_intelligence", {}).get("operator_id") or ""
        )
        if not operator_id:
            raise ExperimentPlanError("operator_scope_unavailable")
        rows = lab.get("research_intelligence", {}).get("experiment_candidates", [])
        candidates = {
            row["key"]: row for row in rows if isinstance(row, dict)
            and isinstance(row.get("key"), str) and row.get("key")
        }
        if len(candidates) != len(rows):
            raise ExperimentPlanError("invalid_experiment_candidates")
        return operator_id, candidates

    def _path(self, operator_id: str) -> Path:
        # Only sha256 of the validated operator id becomes a filename.
        digest = hashlib.sha256(operator_id.encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{digest}.json"

    @staticmethod
    def _snapshot(candidate: dict[str, Any]) -> str:
        content = json.dumps(candidate, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _load(self, operator_id: str) -> dict[str, Any]:
        path = self._path(operator_id)
        if not path.exists():
            return {
                "schema_version": "experiment-plan-v1",
                "operator_id": operator_id,
                "items": {},
            }
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExperimentPlanError("experiment_plan_corrupt") from exc
        if (
            not isinstance(value, dict)
            or value.get("operator_id") != operator_id
            or not isinstance(value.get("items"), dict)
        ):
            raise ExperimentPlanError("experiment_plan_wrong_operator_or_schema")
        return value

    def _save(self, operator_id: str, plan: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest = self._path(operator_id)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".plan-", suffix=".tmp",
            dir=self.directory, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(plan, handle, ensure_ascii=False, indent=2)
        try:
            temporary.replace(dest)
        finally:
            temporary.unlink(missing_ok=True)

    def view(self) -> dict[str, Any]:
        operator_id, candidates = self._candidate_map()
        with self.lock:
            plan = self._load(operator_id)
        items: list[dict[str, Any]] = []
        for key, row in plan["items"].items():
            candidate = candidates.get(key)
            current = bool(
                candidate and self._snapshot(candidate) == row.get("candidate_snapshot")
            )
            items.append({
                **row,
                "key": key,
                "candidate": candidate if candidate else row.get("original_candidate"),
                "is_current": current,
                "needs_recheck": not current,
            })
        return {
            "schema_version": "experiment-plan-v1",
            "operator_id": operator_id,
            "entries": sorted(items, key=lambda row: (row.get("added_at", ""), row["key"])),
            "selected_keys": sorted(plan["items"]),
            "selected_count": len(items),
            "source": "researcher-selected first-party experiments; not operator truth",
        }

    def mutate(
        self, *, key: str, action: str,
        state: str = "planned", notes: str = "",
        metric_observed: str = "",
    ) -> dict[str, Any]:
        if action not in self.ACTIONS:
            raise ExperimentPlanError("invalid_experiment_action")
        if not isinstance(key, str) or not (1 <= len(key) <= 70):
            raise ExperimentPlanError("invalid_experiment_key")
        if state not in self.STATES:
            raise ExperimentPlanError("invalid_experiment_state")
        if any(not isinstance(text, str) or len(text) > self.MAX_NOTES
               for text in (notes, metric_observed)):
            raise ExperimentPlanError("invalid_experiment_notes")
        operator_id, candidates = self._candidate_map()
        candidate = candidates.get(key)
        if action == "add" and candidate is None:
            raise ExperimentPlanError("unknown_experiment_candidate")
        with self.lock:
            plan = self._load(operator_id)
            if action == "add":
                plan["items"][key] = {
                    "key": key,
                    "state": "planned",
                    "added_at": datetime.now(UTC).isoformat(),
                    "candidate_snapshot": self._snapshot(candidate),
                    "original_candidate": candidate,
                    "notes": "",
                    "metric_observed": "",
                    "evidence_not_operator_approval": True,
                }
            elif action == "remove":
                if key not in plan["items"]:
                    raise ExperimentPlanError("experiment_not_selected")
                del plan["items"][key]
            else:
                if key not in plan["items"]:
                    raise ExperimentPlanError("experiment_not_selected")
                row = plan["items"][key]
                if candidate is None or row.get("candidate_snapshot") != self._snapshot(candidate):
                    raise ExperimentPlanError("stale_experiment_requires_reselection")
                row.update({
                    "state": state,
                    "notes": notes.strip(),
                    "metric_observed": metric_observed.strip(),
                    "updated_at": datetime.now(UTC).isoformat(),
                })
            self._save(operator_id, plan)
        return self.view()
