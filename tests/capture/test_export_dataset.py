from __future__ import annotations

import csv
import hashlib
import zipfile
from pathlib import Path

import pytest

from creative_research.capture import export_dataset as exporter
from creative_research.identity import stable_post_id
from creative_research.infrastructure.storage import read_jsonl, write_jsonl


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    selected, media = (tmp_path / name for name in ("selected", "media"))
    posts = [
        {
            "id": "7649340799209065748",
            "input": "creator",
            "isSlideshow": True,
            "slideshowImageLinks": [
                {"tiktokLink": f"https://example.test/{i}.jpg"} for i in range(1, 11)
            ],
            "text": "Tiếng Việt 日本語\ncaption",
            "playCount": 42,
            "authorMeta": {"name": "creator", "avatar": "https://example.test/avatar.jpg"},
            "extra_field": {"untouched": [None, False, 123]},
        },
        {
            "id": "7649340799209065749",
            "input": "creator",
            "isSlideshow": False,
            "text": "video",
            "authorMeta": {"name": "creator"},
        },
    ]
    write_jsonl(selected / "posts/creator.jsonl", posts)
    write_jsonl(
        selected / "normalized/posts.jsonl",
        [
            {
                "account": "creator",
                "post_id": posts[0]["id"],
                "caption": posts[0]["text"],
                "views": 42,
                "extra_normalized": {"preserved": True},
            },
            {"account": "creator", "post_id": posts[1]["id"], "caption": "video"},
        ],
    )
    for post in posts:
        directory = media / "creator" / post["id"]
        directory.mkdir(parents=True)
        (directory / "cover.jpg").write_bytes(b"same-image")
    slideshow = media / "creator" / posts[0]["id"]
    for i in range(1, 11):
        (slideshow / f"slide_{i:03}.jpg").write_bytes(
            b"same-image" if i <= 2 else f"image-{i}".encode()
        )
    profile = media / "creator/profile"
    profile.mkdir()
    (profile / "avatar.jpg").write_bytes(b"avatar")
    video = media / "creator" / posts[1]["id"]
    (video / "video.mp4").write_bytes(b"video-bytes")
    return {
        "input_dir": str(selected),
        "media_root": str(media),
        "out": str(tmp_path / "handoff"),
    }, posts


def test_full_payload_ordered_media_dedup_and_portable_zip(dataset, tmp_path):
    options, raw = dataset
    result = exporter.run(**options, include_zip=True)
    output = Path(options["out"])
    posts = read_jsonl(output / "posts.jsonl")
    assets = {row["asset_id"]: row for row in read_jsonl(output / "assets.jsonl")}
    assert [post["raw"] for post in posts] == raw
    assert posts[0]["metadata"]["extra_normalized"] == {"preserved": True}
    assert posts[0]["post_uid"] == stable_post_id("creator", raw[0]["id"])
    assert [s["index"] for s in posts[0]["media"]["slides"]] == list(range(1, 11))
    assert posts[0]["media"]["slides"][0]["asset_id"] == posts[0]["media"]["covers"][0]
    assert (
        posts[0]["media"]["slides"][0]["asset_id"] == (posts[0]["media"]["slides"][1]["asset_id"])
    )
    assert posts[0]["media"]["avatars"] == posts[1]["media"]["avatars"]
    assert read_jsonl(output / "missing_assets.jsonl") == []
    assert result["counts"]["source_media_files"] == 14
    assert result["counts"]["unique_assets"] == 11
    assert result["counts"]["source_media_by_role"] == {
        "avatar": 1,
        "cover": 2,
        "slide": 10,
        "video": 1,
    }
    assert (output / "posts.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    with (output / "posts.csv").open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["post_id"] == raw[0]["id"]
    assert rows[0]["caption"] == raw[0]["text"]
    with zipfile.ZipFile(result["zip"]) as archive:
        assert archive.testzip() is None
        assert archive.getinfo("handoff/posts.jsonl").compress_type == zipfile.ZIP_DEFLATED
        for asset in assets.values():
            assert archive.getinfo(f"handoff/{asset['path']}").compress_type == zipfile.ZIP_STORED
        archive.extractall(tmp_path / "relocated")
    relocated = tmp_path / "relocated/handoff"
    for line in (relocated / "checksums.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((relocated / name).read_bytes()).hexdigest() == digest
    assert all(not Path(asset["path"]).is_absolute() for asset in assets.values())
    for post in posts:
        refs = [slide["asset_id"] for slide in post["media"]["slides"]]
        for key in ("covers", "avatars", "videos"):
            refs.extend(post["media"][key])
        assert all((relocated / assets[ref]["path"]).is_file() for ref in refs)


def test_missing_and_empty_media_retain_posts(dataset):
    options, raw = dataset
    slides = Path(options["media_root"]) / "creator" / raw[0]["id"]
    (slides / "slide_001.jpg").unlink()
    (slides / "slide_002.jpg").write_bytes(b"")
    (Path(options["media_root"]) / "creator" / raw[1]["id"] / "video.mp4").unlink()
    result = exporter.run(**options)
    output = Path(options["out"])
    missing = read_jsonl(output / "missing_assets.jsonl")
    assert {(r["kind"], r["index"], r["reason"]) for r in missing} == {
        ("slide", 1, "not_found"),
        ("slide", 2, "empty_file"),
        ("video", None, "not_found"),
    }
    assert result["counts"]["posts"] == 2
    assert result["counts"]["empty_media_files"] == 1
    assert result["counts"]["posts_with_missing_assets"] == 2
    assert all(r["media_status"] == "incomplete" for r in read_jsonl(output / "posts.jsonl"))


def test_dry_run_writes_nothing_and_sources_unchanged(dataset, tmp_path):
    options, _ = dataset
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = exporter.run(**options, dry_run=True, include_zip=True)
    assert result["dry_run"] is True
    assert not Path(options["out"]).exists()
    assert not Path(result["zip"]).exists()
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    exporter.run(**options)
    assert all(path.read_bytes() == content for path, content in before.items())


def test_duplicate_rows_collapsed_but_conflicting_selected_payloads_fail(dataset):
    options, raw = dataset
    source = Path(options["input_dir"]) / "posts/creator.jsonl"
    write_jsonl(source, [*raw, raw[0]])
    assert exporter.run(**options, dry_run=True)["counts"]["duplicate_post_rows_removed"] == 1
    write_jsonl(source, [*raw, {**raw[0], "playCount": 999}])
    with pytest.raises(ValueError, match="Conflicting selected payloads"):
        exporter.run(**options)
    assert not Path(options["out"]).exists()


@pytest.mark.parametrize("content", ['{"id":', "[]", '{"input":"creator"}'])
def test_invalid_input_fails_without_publication(dataset, content):
    options, _ = dataset
    (Path(options["input_dir"]) / "posts/creator.jsonl").write_text(content)
    with pytest.raises(ValueError):
        exporter.run(**options)
    assert not Path(options["out"]).exists()


@pytest.mark.parametrize("unsafe", ["../escape", "a/b", "..", "a\\b"])
def test_unsafe_identifiers_rejected_before_writes(dataset, unsafe):
    options, raw = dataset
    write_jsonl(Path(options["input_dir"]) / "posts/creator.jsonl", [{**raw[0], "id": unsafe}])
    with pytest.raises(ValueError):
        exporter.run(**options)
    assert not Path(options["out"]).exists()


def test_symlink_asset_escape_rejected(dataset, tmp_path):
    options, raw = dataset
    slide = Path(options["media_root"]) / "creator" / raw[0]["id"] / "slide_001.jpg"
    slide.unlink()
    external = tmp_path / "private.txt"
    external.write_bytes(b"private-content")
    slide.symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        exporter.run(**options)
    assert not Path(options["out"]).exists()


@pytest.mark.parametrize("zip_collision", [False, True])
def test_existing_outputs_not_overwritten(dataset, zip_collision):
    options, _ = dataset
    path = Path(options["out"] + ".zip") if zip_collision else Path(options["out"])
    path.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="already exists"):
        exporter.run(**options, include_zip=True)
    assert path.read_bytes() == b"preserve"


def test_output_cannot_overlap_source_or_traverse_symlink(dataset, tmp_path):
    options, _ = dataset
    with pytest.raises(ValueError, match="overlaps"):
        exporter.run(**{**options, "out": str(Path(options["input_dir"]) / "export")})
    link = tmp_path / "link"
    link.symlink_to(Path(options["media_root"]), target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        exporter.run(**{**options, "out": str(link / "export")})


@pytest.mark.parametrize("stage", ["copy", "zip", "publication"])
def test_failures_and_interrupts_rollback_outputs(dataset, monkeypatch, stage):
    options, _ = dataset

    def fail(*args, **kwargs):
        raise KeyboardInterrupt()

    if stage == "copy":
        monkeypatch.setattr(exporter._Sources, "copy", fail)
    elif stage == "zip":
        monkeypatch.setattr(exporter, "_write_zip", fail)
    else:
        original = Path.replace

        def replace(path, target):
            if str(target).endswith("handoff.zip"):
                fail()
            return original(path, target)

        monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(KeyboardInterrupt):
        exporter.run(**options, include_zip=True)
    output = Path(options["out"])
    assert not output.exists()
    assert not Path(str(output) + ".zip").exists()
    assert list(output.parent.glob(".dataset-export-*")) == []


def test_source_change_during_copy_cancels_export(dataset, monkeypatch):
    options, raw = dataset
    original = exporter._Sources.copy

    def copy(sources, staged):
        path = Path(options["input_dir"]) / "posts/creator.jsonl"
        write_jsonl(path, [*raw, {"input": "creator", "id": "extra"}])
        original(sources, staged)

    monkeypatch.setattr(exporter._Sources, "copy", copy)
    with pytest.raises(ValueError, match="Source changed"):
        exporter.run(**options)
    assert not Path(options["out"]).exists()


def test_no_normalized_file_uses_raw_and_casefold_media_lookup(dataset):
    options, raw = dataset
    (Path(options["input_dir"]) / "normalized/posts.jsonl").unlink()
    write_jsonl(
        Path(options["input_dir"]) / "posts/creator.jsonl",
        [{**row, "input": "CREATOR"} for row in raw],
    )
    exporter.run(**options)
    posts = read_jsonl(Path(options["out"]) / "posts.jsonl")
    assert posts[0]["account"] == "CREATOR"
    assert posts[0]["metadata"]["caption"] == raw[0]["text"]
    assert posts[0]["media_status"] == "complete"


def test_new_media_during_copy_cancels_export(dataset, monkeypatch):
    options, raw = dataset
    original = exporter._Sources.copy

    def copy(sources, staged):
        path = Path(options["media_root"]) / "creator" / raw[0]["id"] / "slide_011.jpg"
        path.write_bytes(b"new-image")
        original(sources, staged)

    monkeypatch.setattr(exporter._Sources, "copy", copy)
    with pytest.raises(ValueError, match="Source changed"):
        exporter.run(**options)
    assert not Path(options["out"]).exists()


def test_filename_account_fallback_without_normalized_record(dataset):
    options, raw = dataset
    (Path(options["input_dir"]) / "normalized/posts.jsonl").unlink()
    write_jsonl(
        Path(options["input_dir"]) / "posts/creator.jsonl",
        [
            {key: value for key, value in row.items() if key not in {"input", "authorMeta"}}
            for row in raw
        ],
    )
    exporter.run(**options)
    posts = read_jsonl(Path(options["out"]) / "posts.jsonl")
    assert posts[0]["account"] == "creator"
    assert posts[0]["media_status"] == "complete"
