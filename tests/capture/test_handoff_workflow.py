from __future__ import annotations

import hashlib
import json
import shutil
import zipfile

import pytest

from creative_research.capture import media, scrape
from creative_research.capture.export_dataset import run as export
from creative_research.capture.validation import validate_dataset
from creative_research.cli.app import execute
from creative_research.infrastructure.storage import read_jsonl, write_json, write_jsonl


def test_capture_download_export_and_relocate_without_original_sources(capture, capsys):
    root, args, raw, calls, requests = capture
    assert execute(args) == 0
    capsys.readouterr()
    assert len(calls) == 1
    assert read_jsonl(root / "data/raw/run-001/posts/creator.jsonl") == raw
    assert (
        execute(["download-media", "--input", "data/raw/run-001", "--out", "data/media", "--json"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["failed"] == 0 and len(requests) == 5
    first_requests = requests[:]
    assert (
        execute(["download-media", "--input", "data/raw/run-001", "--out", "data/media", "--json"])
        == 0
    )
    resumed = json.loads(capsys.readouterr().out)
    assert requests == first_requests
    assert resumed["videos"]["downloaded_or_cached"] == 1
    assert (
        execute(
            [
                "export-dataset",
                "--input",
                "data/raw/run-001",
                "--media-root",
                "data/media",
                "--out",
                "exports/handoff",
                "--zip",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["capture"]["batches"][0]["run_id"] == "run-1"
    assert result["capture"]["batches"][0]["dataset_id"] == "dataset-1"
    assert result["counts"]["missing_assets"] == 0
    with zipfile.ZipFile(result["zip"]) as archive:
        archive.extractall(root / "recipient")
    shutil.rmtree(root / "data")
    assert execute(["validate", "--dataset", "recipient/handoff", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert [post["raw"] for post in read_jsonl(root / "recipient/handoff/posts.jsonl")] == raw


def test_pipeline_preserves_distinct_handles_with_leading_underscores(capture, capsys):
    root, _, raw, _, _ = capture
    (root / "accounts.txt").write_text("_creator\ncreator\n")
    raw[0]["input"] = "_creator"
    raw[0]["authorMeta"]["name"] = "_creator"
    assert (
        execute(
            [
                "run",
                "--accounts-file",
                "accounts.txt",
                "--out",
                "data/runs/handles",
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    run = root / "data/runs/handles"
    assert read_jsonl(run / "raw/posts/_creator.jsonl") == [raw[0]]
    assert read_jsonl(run / "raw/posts/creator.jsonl") == [raw[1]]
    assert (run / "raw/profiles/_creator.json").is_file()
    assert (run / "media/_creator/profile/avatar.jpg").is_file()
    posts = read_jsonl(root / report["dataset"] / "posts.jsonl")
    assert {post["account"] for post in posts} == {"_creator", "creator"}
    assert report["complete"] and validate_dataset(root / report["dataset"])["ok"]


@pytest.mark.parametrize("identity", ["post_id", "photo_url"])
def test_standalone_post_identity_downloads_and_exports_without_changing_raw(
    capture, capsys, identity
):
    root, _, _, _, _ = capture
    raw = {
        "account": "creator",
        "isSlideshow": identity == "photo_url",
        "videoMeta": {"originalCoverUrl": "https://example.test/cover"},
        "webVideoUrl": "https://www.tiktok.com/@creator/video/7649340799209065748",
    }
    if identity == "post_id":
        raw["post_id"] = "7649340799209065748"
    else:
        raw["webVideoUrl"] = "https://www.tiktok.com/@creator/photo/7649340799209065748"
        raw["slideshowImageLinks"] = [{"tiktokLink": "https://example.test/slide"}]
    write_jsonl(root / "standalone/posts/creator.jsonl", [raw])
    assert execute(["download-media", "--input", "standalone", "--out", "media", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["failed"] == 0
    assert (root / "media/creator/7649340799209065748/cover.jpg").is_file()
    assert (
        execute(
            [
                "export-dataset",
                "--input",
                "standalone",
                "--media-root",
                "media",
                "--out",
                "exports/standalone",
                "--require-verified-media",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["counts"]["missing_assets"] == 0
    posts = read_jsonl(root / "exports/standalone/posts.jsonl")
    assert posts[0]["post_id"] == "7649340799209065748" and posts[0]["raw"] == raw
    assert validate_dataset(root / "exports/standalone")["ok"]


@pytest.mark.parametrize(
    "failure", ["FAILED", "TIMED-OUT", "missing_dataset", "exception", "interrupt"]
)
def test_partial_capture_retains_successful_batches_and_returns_nonzero(
    capture, monkeypatch, failure
):
    root, args, raw, _, _ = capture
    count = 0

    def batch(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}
        if failure == "interrupt":
            raise KeyboardInterrupt
        if failure == "exception":
            raise RuntimeError("synthetic provider failure")
        return {"status": "SUCCEEDED" if failure == "missing_dataset" else failure}

    monkeypatch.setattr(scrape, "run_actor_batch", batch)
    assert execute([*args, "--batch-size", "1"]) == (130 if failure == "interrupt" else 1)
    assert read_jsonl(root / "data/raw/run-001/posts/creator.jsonl") == raw
    manifest = json.loads((root / "data/raw/run-001/manifest.json").read_text())
    assert manifest["interrupted"] if failure == "interrupt" else manifest["failed_batches"]


def test_download_failure_is_reported_and_retry_clears_previous_failures(
    capture, monkeypatch, capsys
):
    root, args, _, _, _ = capture
    assert execute(args) == 0
    capsys.readouterr()
    original = media.fetch_candidate

    async def fail(*args, **kwargs):
        return None, {"source": "fixture", "attempts": [{"http_status": 410}]}

    monkeypatch.setattr(media, "fetch_candidate", fail)
    command = ["download-media", "--input", "data/raw/run-001", "--json"]
    assert execute(command) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == 5
    monkeypatch.setattr(media, "fetch_candidate", original)
    assert execute(command) == 0
    assert json.loads(capsys.readouterr().out)["failed"] == 0
    manifest = read_jsonl(root / "data/media/media_manifest.jsonl")
    assert all(row["status"] != "failed" for row in manifest)


def test_download_dry_run_does_not_create_archive_or_call_network(capture, capsys):
    root, args, _, _, requests = capture
    assert execute(args) == 0
    capsys.readouterr()
    assert execute(["download-media", "--input", "data/raw/run-001", "--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"]
    assert not (root / "data/media").exists() and requests == []


def test_capture_refuses_to_replace_an_existing_snapshot(capture):
    root, args, _, calls, _ = capture
    assert execute(args) == 0
    before = {path: path.read_bytes() for path in (root / "data/raw").rglob("*") if path.is_file()}
    assert execute(args) == 2
    assert len(calls) == 1
    assert all(path.read_bytes() == content for path, content in before.items())


def test_interrupted_capture_rebuild_does_not_keep_previous_completion(capture, monkeypatch):
    root, args, _, calls, _ = capture
    assert execute(args) == 0

    def fail(*args):
        raise OSError("synthetic derived output failure")

    monkeypatch.setattr(scrape, "split_and_write", fail)
    assert execute([*args, "--resume"]) == 1
    info = json.loads((root / "data/raw/run-001/run_info.json").read_text())
    assert "finished_at" not in info and "manifest" not in info
    assert len(calls) == 1
    assert (root / "data/raw/run-001/raw/batches/batch_001_items.jsonl").is_file()


def test_export_rejects_ambiguous_slide_positions_before_publication(tmp_path):
    write_jsonl(
        tmp_path / "crawl/posts/creator.jsonl",
        [{"id": "1", "input": "creator", "isSlideshow": True}],
    )
    media_dir = tmp_path / "media/creator/1"
    media_dir.mkdir(parents=True)
    (media_dir / "slide_001.jpg").write_bytes(b"first")
    (media_dir / "slide_001.png").write_bytes(b"second")
    with pytest.raises(ValueError, match="Ambiguous slide positions"):
        export(
            input_dir=str(tmp_path / "crawl"),
            media_root=str(tmp_path / "media"),
            out=str(tmp_path / "out"),
        )
    assert not (tmp_path / "out").exists()


def test_validation_accepts_inventoried_missing_media_and_rejects_corruption(tmp_path):
    write_jsonl(tmp_path / "crawl/posts/creator.jsonl", [{"id": "1", "input": "creator"}])
    export(
        input_dir=str(tmp_path / "crawl"),
        media_root=str(tmp_path / "media"),
        out=str(tmp_path / "out"),
    )
    assert validate_dataset(tmp_path / "out")["ok"]
    (tmp_path / "out/posts.csv").write_text("corrupt")
    report = validate_dataset(tmp_path / "out")
    assert not report["ok"] and "Checksum mismatch" in report["issues"][0]


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "duplicate",
        "numeric_id",
        "unknown_asset",
        "slide_order",
        "missing_status",
        "counts",
        "raw_type",
        "extra_file",
        "asset_size",
        "asset_identity",
        "unsafe_path",
        "completion_without_capture",
        "capture_disagreement",
        "numeric_capture_completion",
    ],
)
def test_validator_rejects_tampered_contract_even_with_updated_checksums(tmp_path, mutation):
    write_jsonl(tmp_path / "crawl/posts/creator.jsonl", [{"id": "1", "input": "creator"}])
    asset = tmp_path / "media/creator/1/cover.jpg"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"image")
    out = tmp_path / "out"
    export(input_dir=str(tmp_path / "crawl"), media_root=str(tmp_path / "media"), out=str(out))
    posts = read_jsonl(out / "posts.jsonl")
    assets = read_jsonl(out / "assets.jsonl")
    manifest = json.loads((out / "manifest.json").read_text())
    if mutation == "schema":
        manifest["schema_version"] = "unknown"
    if mutation == "duplicate":
        posts.append(posts[0])
    if mutation == "numeric_id":
        posts[0]["post_id"] = 1
    if mutation == "unknown_asset":
        posts[0]["media"]["covers"] = ["missing"]
    if mutation == "slide_order":
        posts[0]["media"]["slides"] = [
            {"index": 2, "asset_id": assets[0]["asset_id"]},
            {"index": 1, "asset_id": assets[0]["asset_id"]},
        ]
    if mutation == "missing_status":
        posts[0]["media_status"] = "complete"
    if mutation == "counts":
        manifest["counts"]["posts"] = 99
    if mutation == "raw_type":
        posts[0]["raw"] = "invalid"
    if mutation == "extra_file":
        (out / "unlisted.txt").write_text("unexpected")
    if mutation == "asset_size":
        assets[0]["bytes"] = 99
    if mutation == "asset_identity":
        assets[0]["asset_id"] = "renamed"
        posts[0]["media"]["covers"] = ["renamed"]
    if mutation == "unsafe_path":
        assets[0]["path"] = "assets/../../outside"
    if mutation in {"completion_without_capture", "capture_disagreement"}:
        manifest["completion"]["capture"] = True
        manifest["completion"]["complete"] = manifest["completion"]["media"]
    if mutation in {"capture_disagreement", "numeric_capture_completion"}:
        manifest["capture"] = {"complete": False}
    if mutation == "numeric_capture_completion":
        manifest["completion"]["capture"] = 0
    write_jsonl(out / "posts.jsonl", posts)
    write_jsonl(out / "assets.jsonl", assets)
    write_json(out / "manifest.json", manifest)
    checksums = {
        line.split("  ", 1)[1]: line.split("  ", 1)[0]
        for line in (out / "checksums.sha256").read_text().splitlines()
    }
    for name in checksums:
        checksums[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / "checksums.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items()))
    )
    assert not validate_dataset(out)["ok"]
