"""Durable acquisition pipeline: capture, archive, publish, verify."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from creative_research.capture import download, export_dataset, scrape
from creative_research.capture.cache import fingerprint, source_fingerprint
from creative_research.capture.contracts import PIPELINE_STAGES, PIPELINE_STATE_SCHEMA_VERSION
from creative_research.capture.validation import validate_dataset
from creative_research.errors import ApplicationError
from creative_research.infrastructure.locking import project_writer
from creative_research.infrastructure.logging import redact
from creative_research.infrastructure.paths import confined_path, project_root, resolve_path
from creative_research.infrastructure.storage import read_json_object, write_json, write_text

DEFAULTS: dict[str, Any] = {
    "batch_size": 4,
    "max_posts": 10000,
    "actor_timeout": 7200,
    "max_charge_usd": None,
    "oldest_date": None,
    "newest_date": None,
    "concurrency": 12,
    "timeout": 35.0,
    "retries": 1,
    "include_zip": False,
}


@dataclass(frozen=True, slots=True)
class PipelineOptions:
    out: str
    accounts_file: str | None = None
    resume: bool = False
    allow_partial: bool = False
    batch_size: int | None = None
    max_posts: int | None = None
    actor_timeout: int | None = None
    max_charge_usd: float | None = None
    oldest_date: str | None = None
    newest_date: str | None = None
    concurrency: int | None = None
    timeout: float | None = None
    retries: int | None = None
    include_zip: bool | None = None
    cookies_from_browser: str | None = None
    cookies_file: str | None = None
    recover_runs: list[str] | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def read_run(out: Path) -> dict[str, Any]:
    if any(
        (out / name).is_symlink()
        for name in ("pipeline.json", "accounts.txt", "raw", "media", "datasets")
    ):
        raise ValueError("Pipeline checkpoints must not traverse symlinks")
    state = read_json_object(out / "pipeline.json")
    stages, config = state.get("stages"), state.get("config")
    statuses = {"pending", "running", "completed", "partial", "failed", "interrupted"}
    if (
        state.get("schema_version") != PIPELINE_STATE_SCHEMA_VERSION
        or not isinstance(stages, dict)
        or set(stages) != set(PIPELINE_STAGES)
        or not isinstance(config, dict)
        or not set(DEFAULTS).union({"accounts"}).issubset(config)
        or not isinstance(config["accounts"], list)
        or not config["accounts"]
        or not all(isinstance(account, str) and account for account in config["accounts"])
        or not isinstance(state.get("run_id"), str)
        or not re.fullmatch(r"[0-9a-f]{32}", state["run_id"])
        or not isinstance(state.get("status"), str)
        or state["status"] not in statuses
        or type(state.get("publication")) is not int
        or state["publication"] < 0
    ):
        raise ValueError("Unsupported or invalid pipeline checkpoint")
    if state.get("config_fingerprint") != fingerprint(config):
        raise ValueError("Pipeline configuration checkpoint changed")
    for name, item in stages.items():
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("status"), str)
            or item["status"] not in statuses
            or type(item.get("attempts")) is not int
            or item["attempts"] < 0
            or ("result" in item and not isinstance(item["result"], dict))
            or (
                name == "scrape"
                and item["status"] == "completed"
                and not isinstance(item.get("result", {}).get("source_fingerprint"), str)
            )
        ):
            raise ValueError(f"Invalid pipeline stage checkpoint: {name}")
        if "output" in item and (
            not isinstance(item["output"], str)
            or not re.fullmatch(r"datasets/\d{4,}", item["output"])
        ):
            raise ValueError("Invalid publication path in pipeline checkpoint")
    return state


def _capture_options(
    root: Path,
    config: dict[str, Any],
    options: PipelineOptions,
    *,
    resume: bool,
    preflight: bool = False,
) -> scrape.ScrapeOptions:
    return scrape.ScrapeOptions(
        accounts_file=str(root / "accounts.txt"),
        out=str(root / "raw"),
        token=None,
        batch_size=config["batch_size"],
        max_posts=config["max_posts"],
        actor_timeout=config["actor_timeout"],
        max_charge_usd=config["max_charge_usd"],
        comments=0,
        top_level_comments=0,
        max_replies=0,
        oldest_date=config["oldest_date"],
        newest_date=config["newest_date"],
        preflight=preflight,
        resume=resume,
        recover_runs=options.recover_runs,
    )


def run(options: PipelineOptions) -> dict[str, Any]:
    requested = Path(options.out).expanduser()
    if not requested.is_absolute():
        requested = project_root() / requested
    if any(path.is_symlink() for path in (requested, *requested.parents)):
        raise ValueError("Pipeline output must not traverse symlinks")
    root = resolve_path(options.out)
    with project_writer():
        if options.resume:
            state = read_run(root)
            config = state["config"]
            for key in DEFAULTS:
                value = getattr(options, key)
                if value is not None and value != config[key]:
                    raise ValueError(f"Resume cannot change {key}; create a new run")
            if (
                options.accounts_file
                and scrape.read_accounts(resolve_path(options.accounts_file)) != config["accounts"]
            ):
                raise ValueError("Resume cannot change accounts; create a new run")
            if scrape.read_accounts(root / "accounts.txt") != config["accounts"]:
                raise ValueError("Saved pipeline accounts changed")
        else:
            if root.exists() and (not root.is_dir() or any(root.iterdir())):
                raise ValueError("Pipeline output already exists; use --resume or a new directory")
            if not options.accounts_file:
                raise ValueError("A new run requires --accounts-file")
            config = {
                key: getattr(options, key) if getattr(options, key) is not None else value
                for key, value in DEFAULTS.items()
            }
            config["accounts"] = scrape.read_accounts(resolve_path(options.accounts_file))
            if not config["accounts"]:
                raise ValueError("Accounts file is empty")
            if (
                any(
                    config[key] < 1
                    for key in ("batch_size", "max_posts", "actor_timeout", "concurrency")
                )
                or config["retries"] < 0
            ):
                raise ValueError("Limits must be positive; retries cannot be negative")
            if not math.isfinite(config["timeout"]) or config["timeout"] <= 0:
                raise ValueError("Download timeout must be finite and positive")
            cap = config["max_charge_usd"]
            if cap is not None and (not math.isfinite(cap) or cap <= 0):
                raise ValueError("Charge cap must be finite and positive")
            for account in config["accounts"]:
                confined_path(root / "raw/posts", f"{account}.jsonl")
            root.mkdir(parents=True, exist_ok=True)
            write_text(root / "accounts.txt", "\n".join(config["accounts"]) + "\n")
            state = {
                "schema_version": PIPELINE_STATE_SCHEMA_VERSION,
                "run_id": uuid4().hex,
                "created_at": _now(),
                "config": config,
                "config_fingerprint": fingerprint(config),
                "status": "pending",
                "stages": {
                    stage: {"status": "pending", "attempts": 0} for stage in PIPELINE_STAGES
                },
                "publication": 0,
            }
        return _run(root, state, options)


def _run(root: Path, state: dict[str, Any], options: PipelineOptions) -> dict[str, Any]:
    def save() -> None:
        state["updated_at"] = _now()
        write_json(root / "pipeline.json", state)

    def stage(name: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        checkpoint = state["stages"][name]
        checkpoint.update(status="running", started_at=_now(), attempts=checkpoint["attempts"] + 1)
        checkpoint.pop("error", None)
        checkpoint.pop("result", None)
        save()
        try:
            result = action()
        except BaseException as exc:
            checkpoint.update(
                status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                finished_at=_now(),
                error=redact(f"{type(exc).__name__}: {exc}"),
            )
            save()
            raise
        incomplete = bool(result.get("failed") or result.get("counts", {}).get("missing_assets"))
        checkpoint.update(
            status="partial" if incomplete else "completed", finished_at=_now(), result=result
        )
        save()
        return result

    state.update(status="running", complete=False, allow_partial=options.allow_partial)
    state.pop("error", None)
    save()
    try:
        capture_stage = state["stages"]["scrape"]
        capture_complete = capture_stage["status"] == "completed"
        if capture_complete:
            if capture_stage["result"]["source_fingerprint"] != source_fingerprint(root / "raw"):
                raise ValueError("Completed capture snapshot changed; create a new run")
        else:

            def capture() -> dict[str, Any]:
                manifest = scrape.archive_posts(
                    _capture_options(
                        root,
                        state["config"],
                        options,
                        resume=(root / "raw/run_info.json").is_file(),
                    )
                )
                return {
                    "source_fingerprint": source_fingerprint(root / "raw"),
                    "manifest": manifest,
                }

            try:
                stage("scrape", capture)
                capture_complete = True
            except ApplicationError:
                if not options.allow_partial:
                    raise
                capture_complete = False
        raw_fingerprint = source_fingerprint(root / "raw")

        def archive() -> dict[str, Any]:
            config = state["config"]
            result = download.run(
                download.DownloadOptions(
                    input=str(root / "raw"),
                    out=str(root / "media"),
                    concurrency=config["concurrency"],
                    timeout=config["timeout"],
                    retries=config["retries"],
                    cookies_from_browser=options.cookies_from_browser,
                    cookies_file=options.cookies_file,
                )
            )
            if result["failed"] and not options.allow_partial:
                raise ApplicationError(
                    "Media downloads failed; resume to retry missing/corrupt files"
                )
            return result

        media = stage("download", archive)
        inputs = fingerprint(
            {
                "capture": raw_fingerprint,
                "assets": media["assets"],
                "capture_complete": capture_complete,
            }
        )
        export_stage = state["stages"]["export"]
        reusable = export_stage.get("inputs") == inputs and export_stage.get("output")
        destination = root / export_stage["output"] if reusable else None
        if destination is not None and destination.exists():
            valid = validate_dataset(destination)
            if not valid["ok"]:
                raise ApplicationError(f"Existing dataset failed validation: {valid['issues']}")
            if valid["missing_assets"] and not options.allow_partial:
                raise ApplicationError(
                    "Existing dataset is partial; use --allow-partial to accept its gaps"
                )
            manifest = read_json_object(destination / "manifest.json")
            if manifest.get("pipeline", {}).get("inputs_fingerprint") != inputs:
                raise ValueError("Published dataset does not match pipeline inputs")
            export_stage["status"] = "partial" if valid["missing_assets"] else "completed"
            export_stage.pop("error", None)
            export_stage.setdefault("result", {"output": str(destination), "recovered": True})
        else:
            if not reusable:
                state["publication"] += 1
                export_stage.update(inputs=inputs, output=f"datasets/{state['publication']:04d}")
            destination = root / export_stage["output"]
            lineage = {
                "run_id": state["run_id"],
                "inputs_fingerprint": inputs,
                "capture_fingerprint": raw_fingerprint,
            }

            def publish() -> dict[str, Any]:
                dry = export_dataset.run(
                    input_dir=str(root / "raw"),
                    media_root=str(root / "media"),
                    out=str(destination),
                    dry_run=True,
                    require_verified_media=True,
                    lineage=lineage,
                )
                if dry["counts"]["missing_assets"] and not options.allow_partial:
                    raise ApplicationError(
                        "Required media is missing; use --resume or explicitly --allow-partial"
                    )
                return export_dataset.run(
                    input_dir=str(root / "raw"),
                    media_root=str(root / "media"),
                    out=str(destination),
                    require_verified_media=True,
                    lineage=lineage,
                )

            stage("export", publish)

        def validate() -> dict[str, Any]:
            report = validate_dataset(destination)
            if not report["ok"]:
                raise ApplicationError(f"Dataset validation failed: {report['issues']}")
            if state["config"]["include_zip"]:
                report["zip"] = str(export_dataset.ensure_zip(destination))
            return report

        validation = stage("validate", validate)
        complete = capture_complete and not media["failed"] and not validation["missing_assets"]
        state.update(
            status="completed" if complete else "partial",
            dataset=str(destination),
            complete=complete,
            finished_at=_now(),
        )
    except KeyboardInterrupt:
        state.update(status="interrupted", complete=False, error="Interrupted; resume this run")
    except (Exception, SystemExit) as exc:
        state.update(status="failed", complete=False, error=redact(f"{type(exc).__name__}: {exc}"))
    save()
    return state
