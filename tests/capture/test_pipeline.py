from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from creative_research.capture import export_dataset, media, pipeline, scrape
from creative_research.capture.download import DownloadOptions
from creative_research.capture.download import run as download
from creative_research.capture.validation import validate_dataset
from creative_research.cli.app import execute
from creative_research.infrastructure.storage import (
    read_json_object,
    read_jsonl,
    write_json,
    write_jsonl,
)


def options(capture, **kwargs):
    root, _, _, _, _ = capture
    return pipeline.PipelineOptions(
        out=str(root / "data/runs/001"), accounts_file=str(root / "accounts.txt"), **kwargs
    )


def test_one_command_pipeline_publishes_valid_portable_dataset_and_resumes_without_requests(
    capture, capsys
):
    root, _, posts, calls, requests = capture
    arguments = [
        "run",
        "--accounts-file",
        "accounts.txt",
        "--out",
        "data/runs/001",
        "--max-posts",
        "2",
        "--max-charge-usd",
        "0.5",
        "--zip",
        "--json",
    ]
    assert execute(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed" and result["complete"]
    assert all(stage["status"] == "completed" for stage in result["stages"].values())
    assert len(calls) == 1 and len(requests) == 5
    assert not any(
        calls[0][key]
        for key in (
            "shouldDownloadCovers",
            "shouldDownloadAvatars",
            "shouldDownloadSlideshowImages",
        )
    )
    dataset = Path(result["dataset"])
    assert [post["raw"] for post in read_jsonl(dataset / "posts.jsonl")] == posts
    manifest = read_json_object(dataset / "manifest.json")
    assert manifest["completion"]["complete"] and manifest["pipeline"]["run_id"] == result["run_id"]
    before = list(requests)
    assert execute(["run", "--out", "data/runs/001", "--resume", "--json"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["dataset"] == result["dataset"] and len(calls) == 1 and requests == before
    assert execute(["status", "--run", "data/runs/001", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    with zipfile.ZipFile(dataset.with_suffix(".zip")) as archive:
        archive.extractall(root / "recipient")
    shutil.rmtree(root / "data")
    assert validate_dataset(root / "recipient" / dataset.name)["ok"]


def test_resume_retains_started_apify_run_after_interrupt(capture, monkeypatch):
    _, _, _, calls, _ = capture
    original = scrape.wait_actor_run
    monkeypatch.setattr(
        scrape, "wait_actor_run", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    initial = pipeline.run(options(capture))
    assert initial["status"] == "interrupted" and len(calls) == 1
    raw = Path(options(capture).out) / "raw"
    assert read_json_object(raw / "run_info.json")["batches"][0]["run_id"] == "run-1"
    monkeypatch.setattr(scrape, "wait_actor_run", original)
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "completed" and len(calls) == 1


def test_resume_redownloads_dataset_after_fetch_failure_without_new_paid_run(capture, monkeypatch):
    original = scrape.download_dataset_items
    monkeypatch.setattr(
        scrape,
        "download_dataset_items",
        lambda *args: (_ for _ in ()).throw(RuntimeError("read failed")),
    )
    assert pipeline.run(options(capture))["status"] == "failed"
    monkeypatch.setattr(scrape, "download_dataset_items", original)
    assert pipeline.run(replace(options(capture), resume=True))["status"] == "completed"
    assert len(capture[3]) == 1


def test_uncertain_start_is_not_repeated_and_can_attach_known_run(capture, monkeypatch):
    original = scrape.run_actor_batch
    monkeypatch.setattr(
        scrape,
        "run_actor_batch",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("response lost")),
    )
    first = pipeline.run(options(capture))
    assert first["status"] == "failed"
    monkeypatch.setattr(scrape, "run_actor_batch", original)
    resume = replace(options(capture), resume=True)
    assert pipeline.run(resume)["status"] == "failed"
    assert capture[3] == []
    recovered = pipeline.run(replace(resume, recover_runs=["1=run-1"]))
    assert recovered["status"] == "completed" and capture[3] == []


@pytest.mark.parametrize("status", [401, 403, 500])
def test_auth_rejected_launch_can_retry_but_server_error_stays_uncertain(
    capture, monkeypatch, status
):
    import httpx
    from apify_client.errors import ApifyApiError

    original = scrape.run_actor_batch

    def fail(**kwargs):
        raise ApifyApiError(
            httpx.Response(status, json={"error": {"message": "synthetic rejection"}}),
            1,
            method="POST",
        )

    monkeypatch.setattr(scrape, "run_actor_batch", fail)
    assert pipeline.run(options(capture))["status"] == "failed"
    info = read_json_object(Path(options(capture).out) / "raw/run_info.json")
    assert info["batches"][0]["checkpoint"] == (
        "launch_rejected" if status in {401, 403} else "launch_unknown"
    )
    monkeypatch.setattr(scrape, "run_actor_batch", original)
    resumed = pipeline.run(replace(options(capture), resume=True))
    if status in {401, 403}:
        assert resumed["status"] == "completed" and len(capture[3]) == 1
    else:
        assert resumed["status"] == "failed" and not capture[3]


def test_known_failed_batch_retries_while_successful_batch_is_reused(capture, monkeypatch):
    original = scrape.run_actor_batch
    started = []

    def batch(**kwargs):
        started.append(kwargs["profiles"])
        if kwargs["profiles"] == ["other"] and len(started) == 2:
            return {"id": "failed-run", "status": "FAILED"}
        return original(**kwargs)

    monkeypatch.setattr(scrape, "run_actor_batch", batch)
    configured = options(capture, batch_size=1)
    assert pipeline.run(configured)["status"] == "failed"
    assert pipeline.run(replace(configured, resume=True))["status"] == "completed"
    assert started == [["creator"], ["other"], ["other"]]


def test_download_failures_block_publication_and_resume_retries_only_failed_files(
    capture, monkeypatch
):
    original = media.fetch_candidate

    async def fetch(**kwargs):
        if kwargs["candidate"]["url"].endswith("slide1"):
            return None, {"source": "fixture", "attempts": []}
        return await original(**kwargs)

    monkeypatch.setattr(media, "fetch_candidate", fetch)
    first = pipeline.run(options(capture))
    assert first["status"] == "failed" and first["stages"]["download"]["status"] == "failed"
    assert not list((Path(options(capture).out) / "datasets").glob("*"))
    requests = len(capture[4])
    monkeypatch.setattr(media, "fetch_candidate", original)
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert (
        resumed["status"] == "completed"
        and len(capture[4]) == requests + 1
        and len(capture[3]) == 1
    )


def test_partial_export_is_explicit_nonzero_and_retry_creates_new_immutable_revision(
    capture, monkeypatch, capsys
):
    original = media.fetch_candidate

    async def failed(**kwargs):
        return None, {"source": "fixture", "attempts": []}

    monkeypatch.setattr(media, "fetch_candidate", failed)
    assert (
        execute(
            [
                "run",
                "--accounts-file",
                "accounts.txt",
                "--out",
                "data/runs/001",
                "--allow-partial",
                "--json",
            ]
        )
        == 1
    )
    initial = json.loads(capsys.readouterr().out)
    assert initial["status"] == "partial" and not initial["complete"]
    old_dataset = Path(initial["dataset"])
    old_files = {p: p.read_bytes() for p in old_dataset.rglob("*") if p.is_file()}
    assert validate_dataset(old_dataset)["ok"]
    assert not read_json_object(old_dataset / "manifest.json")["completion"]["complete"]
    monkeypatch.setattr(media, "fetch_candidate", original)
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "completed" and resumed["dataset"] != initial["dataset"]
    assert all(p.read_bytes() == value for p, value in old_files.items())
    assert len(capture[3]) == 1


@pytest.mark.parametrize("kind", ["cover", "video"])
def test_corrupt_media_cache_is_repaired_on_resume(capture, monkeypatch, kind):
    initial = pipeline.run(options(capture))
    assert initial["status"] == "completed"
    root = Path(options(capture).out)
    target = (
        root / "media/creator/7649340799209065748/cover.jpg"
        if kind == "cover"
        else root / "media/creator/7649340799209065749/video.mp4"
    )
    original = target.read_bytes()
    target.write_bytes(b"bad-but-nonempty")
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "completed" and target.read_bytes() == original
    assert resumed["dataset"] == initial["dataset"] and len(capture[3]) == 1


def test_changed_source_does_not_reuse_media_and_failed_stale_file_is_excluded(
    capture, monkeypatch
):
    root, args, posts, _, requests = capture
    assert execute(args) == 0
    opts = DownloadOptions(input="data/raw/run-001", out="data/media")
    assert download(opts)["failed"] == 0
    posts[0]["videoMeta"]["originalCoverUrl"] = "https://example.test/new-cover"
    write_jsonl(root / "data/raw/run-001/posts/creator.jsonl", posts)
    original = media.fetch_candidate

    async def fetch(**kwargs):
        if kwargs["candidate"]["url"].endswith("new-cover"):
            return None, {"source": "fixture", "attempts": []}
        return await original(**kwargs)

    monkeypatch.setattr(media, "fetch_candidate", fetch)
    assert download(opts)["failed"] == 1
    assert (root / "data/media/creator/7649340799209065748/cover.jpg").exists()
    exported = export_dataset.run(
        input_dir=str(root / "data/raw/run-001"),
        media_root=str(root / "data/media"),
        out=str(root / "exports/partial"),
        require_verified_media=True,
    )
    assert exported["counts"]["missing_assets"] == 1
    assert read_jsonl(root / "exports/partial/posts.jsonl")[0]["media"]["covers"] == []


def test_export_validation_failure_prevents_publication(capture, monkeypatch):
    monkeypatch.setattr(
        export_dataset,
        "validate_dataset",
        lambda path: {"ok": False, "issues": ["synthetic rejection"]},
    )
    result = pipeline.run(options(capture))
    assert result["status"] == "failed" and result["stages"]["export"]["status"] == "failed"
    assert not (Path(options(capture).out) / "datasets/0001").exists()


def test_resume_recovers_zip_failure_without_new_capture_or_export(capture, monkeypatch):
    original = export_dataset.ensure_zip
    monkeypatch.setattr(
        export_dataset,
        "ensure_zip",
        lambda path: (_ for _ in ()).throw(OSError("zip disk failure")),
    )
    configured = options(capture, include_zip=True)
    first = pipeline.run(configured)
    assert first["status"] == "failed" and first["stages"]["validate"]["status"] == "failed"
    monkeypatch.setattr(export_dataset, "ensure_zip", original)
    resumed = pipeline.run(replace(configured, resume=True))
    assert resumed["status"] == "completed" and len(capture[3]) == 1
    assert resumed["stages"]["export"]["attempts"] == 1


def test_completed_capture_and_published_dataset_tampering_are_rejected(capture):
    result = pipeline.run(options(capture))
    root = Path(options(capture).out)
    (Path(result["dataset"]) / "posts.csv").write_text("tampered")
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "failed" and "validation" in resumed["error"]
    (root / "raw/posts/creator.jsonl").write_text("{}\n")
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "failed" and "snapshot changed" in resumed["error"]
    assert len(capture[3]) == 1


def test_resume_rejects_changed_configuration_and_checkpoint_paths(capture):
    assert pipeline.run(options(capture))["status"] == "completed"
    with pytest.raises(ValueError, match="cannot change"):
        pipeline.run(replace(options(capture), resume=True, max_posts=1))
    root = Path(options(capture).out)
    state = pipeline.read_run(root)
    state["stages"]["export"]["output"] = "../../outside"
    write_json(root / "pipeline.json", state)
    with pytest.raises(ValueError, match="publication path"):
        pipeline.run(replace(options(capture), resume=True))
    assert len(capture[3]) == 1


def test_standalone_scrape_can_recover_corrupt_batch_from_existing_dataset(capture):
    root, args, posts, calls, _ = capture
    assert execute(args) == 0
    path = root / "data/raw/run-001/raw/batches/batch_001_items.jsonl"
    path.write_text("corrupt\n")
    assert execute([*args, "--resume"]) == 0
    assert read_jsonl(path) == posts and len(calls) == 1


def test_resume_recovers_published_folder_after_interrupted_export_checkpoint(capture, monkeypatch):
    original = export_dataset.run

    def interrupted(**kwargs):
        result = original(**kwargs)
        if not kwargs.get("dry_run"):
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr(export_dataset, "run", interrupted)
    first = pipeline.run(options(capture))
    assert first["status"] == "interrupted"
    assert (Path(options(capture).out) / "datasets/0001").exists()
    monkeypatch.setattr(export_dataset, "run", original)
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "completed" and len(capture[3]) == 1
    assert resumed["stages"]["export"]["attempts"] == 1


def test_missing_required_media_blocks_export_even_if_no_download_job_exists(capture):
    capture[2][0]["videoMeta"] = {}
    result = pipeline.run(options(capture))
    assert result["status"] == "failed" and result["stages"]["export"]["status"] == "failed"
    assert not (Path(options(capture).out) / "datasets/0001").exists()


def test_partial_capture_manifest_remains_partial_and_resume_recovers_failed_batch(
    capture, monkeypatch
):
    original = scrape.run_actor_batch

    def batch(**kwargs):
        if kwargs["profiles"] == ["other"]:
            return {"id": "failed", "status": "FAILED"}
        return original(**kwargs)

    monkeypatch.setattr(scrape, "run_actor_batch", batch)
    configured = options(capture, batch_size=1, allow_partial=True)
    first = pipeline.run(configured)
    assert first["status"] == "partial"
    manifest = read_json_object(Path(first["dataset"]) / "manifest.json")
    assert not manifest["completion"]["capture"] and manifest["completion"]["media"]
    monkeypatch.setattr(scrape, "run_actor_batch", original)
    resumed = pipeline.run(replace(configured, resume=True, allow_partial=False))
    assert resumed["status"] == "completed" and resumed["dataset"] != first["dataset"]


def test_run_validation_failure_cannot_report_completion(capture, monkeypatch):
    monkeypatch.setattr(
        pipeline, "validate_dataset", lambda path: {"ok": False, "issues": ["final rejection"]}
    )
    result = pipeline.run(options(capture))
    assert result["status"] == "failed" and result["stages"]["validate"]["status"] == "failed"


def test_corrupt_existing_zip_is_rejected(capture):
    initial = pipeline.run(options(capture, include_zip=True))
    archive = Path(initial["dataset"]).with_suffix(".zip")
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("extra", "tampered")
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "failed" and "ZIP inventory" in resumed["error"]
    assert len(capture[3]) == 1


def test_provider_row_errors_are_retained_but_never_reported_as_complete(capture):
    capture[2].append({"input": "other", "error": "Profile unavailable", "errorCode": "not_found"})
    first = pipeline.run(options(capture, allow_partial=True))
    assert first["status"] == "partial"
    dataset = Path(first["dataset"])
    assert len(read_jsonl(dataset / "posts.jsonl")) == 2
    manifest = read_json_object(dataset / "manifest.json")
    assert not manifest["completion"]["capture"] and manifest["capture"]["error_records"] == 1
    assert (
        read_jsonl(Path(options(capture).out) / "raw/raw/errors.jsonl")[0]["errorCode"]
        == "not_found"
    )


@pytest.mark.parametrize(
    "values",
    [
        {"max_posts": 0},
        {"concurrency": 0},
        {"max_charge_usd": float("nan")},
        {"timeout": float("inf")},
        {"retries": -1},
    ],
)
def test_invalid_run_limits_fail_before_provider_or_output(capture, values):
    with pytest.raises(ValueError):
        pipeline.run(options(capture, **values))
    assert not Path(options(capture).out).exists() and not capture[3] and not capture[4]


@pytest.mark.parametrize(
    "mutation",
    [
        "stages",
        "stage",
        "stage_status",
        "attempts",
        "result",
        "capture_result",
        "output",
        "status",
        "config",
    ],
)
def test_malformed_checkpoint_is_rejected_without_provider_calls_or_writes(capture, mutation):
    assert pipeline.run(options(capture))["status"] == "completed"
    root = Path(options(capture).out)
    state = pipeline.read_run(root)
    if mutation == "stages":
        state["stages"] = list(state["stages"])
    elif mutation == "stage":
        state["stages"]["download"] = []
    elif mutation == "stage_status":
        state["stages"]["download"]["status"] = []
    elif mutation == "attempts":
        state["stages"]["download"]["attempts"] = True
    elif mutation == "result":
        state["stages"]["download"]["result"] = []
    elif mutation == "capture_result":
        state["stages"]["scrape"].pop("result")
    elif mutation == "output":
        state["stages"]["export"]["output"] = 1
    elif mutation == "status":
        state["status"] = []
    else:
        state["config"] = []
    write_json(root / "pipeline.json", state)
    before = (root / "pipeline.json").read_bytes()
    requests = list(capture[4])
    with pytest.raises(ValueError, match="checkpoint"):
        pipeline.run(replace(options(capture), resume=True))
    assert (root / "pipeline.json").read_bytes() == before
    assert len(capture[3]) == 1 and capture[4] == requests


def test_failed_resume_clears_previous_completion_and_stage_result(capture, monkeypatch):
    assert pipeline.run(options(capture))["status"] == "completed"
    actual_write = pipeline.write_json

    def write(path, state):
        if state["status"] == "running":
            assert state["complete"] is False
        actual_write(path, state)

    def fail(*args):
        raise OSError("synthetic download disk failure")

    monkeypatch.setattr(pipeline, "write_json", write)
    monkeypatch.setattr(pipeline.download, "run", fail)
    resumed = pipeline.run(replace(options(capture), resume=True))
    assert resumed["status"] == "failed" and not resumed["complete"]
    assert resumed["stages"]["download"]["status"] == "failed"
    assert "result" not in resumed["stages"]["download"]
    assert len(capture[3]) == 1
