from __future__ import annotations

import json
from pathlib import Path

import pytest

from creative_research.capture import videos as download_videos
from creative_research.cli.commands.download_videos import main


@pytest.mark.parametrize("mode", ["success", "failed", "timeout"])
def test_ytdlp_stages_outputs_and_never_reports_failed_download_as_cached_success(
    tmp_path, monkeypatch, mode
) -> None:
    from types import SimpleNamespace

    old = tmp_path / "video.mp4"
    old.write_bytes(b"old-complete-video")

    def run(command, **kwargs):
        staged = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp4"))
        staged.write_bytes(b"new-complete-video")
        assert kwargs["timeout"] > 0
        if mode == "timeout":
            raise download_videos.subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(returncode=0 if mode == "success" else 1, stdout="synthetic failure")

    monkeypatch.setattr(download_videos.subprocess, "run", run)
    video, error = download_videos.download_ytdlp(
        "https://www.tiktok.com/@synthetic/video/1", tmp_path, None, None
    )
    if mode == "success":
        assert video == old and error is None
        assert old.read_bytes() == b"new-complete-video"
    else:
        assert video is None and error
        assert old.read_bytes() == b"old-complete-video"
    assert list(tmp_path.iterdir()) == [old]


def test_failed_direct_download_cleans_partial_file_and_keeps_old_video(
    tmp_path, monkeypatch
) -> None:
    import io

    old = tmp_path / "video.mp4"
    old.write_bytes(b"old-complete-video")

    class Response(io.BytesIO):
        headers = {"Content-Type": "video/mp4"}

    monkeypatch.setattr(
        download_videos.urllib.request, "urlopen", lambda *a, **k: Response(b"too-small")
    )
    video, error = download_videos.download_direct(["https://example.test/video.mp4"], tmp_path)
    assert video is None and "too small" in error
    assert old.read_bytes() == b"old-complete-video"
    assert list(tmp_path.iterdir()) == [old]


@pytest.mark.parametrize("post_id", ["../../escape", None, "..", "a\\b"])
def test_video_download_rejects_unsafe_ids_before_starting_downloads(
    tmp_path: Path,
    monkeypatch,
    post_id: str | None,
) -> None:
    post_id = post_id if post_id is not None else str(tmp_path / "escape")
    source = tmp_path / "input/creator/source-post"
    source.mkdir(parents=True)
    (source / "meta.json").write_text(
        json.dumps(
            {
                "post_id": post_id,
                "is_slideshow": False,
                "url": "https://www.tiktok.com/@creator/video/123",
            }
        ),
        encoding="utf-8",
    )
    downloads = []

    def download(*args):
        downloads.append(args)
        return None, "synthetic download disabled"

    monkeypatch.setattr(download_videos, "download_ytdlp", download)
    monkeypatch.setattr(download_videos, "download_direct", download)
    output = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            "download-videos",
            str(tmp_path / "input"),
            "--out",
            str(output),
        ],
    )
    with pytest.raises(ValueError, match="unsafe_path_component"):
        main()
    assert downloads == []
    assert not list(output.iterdir())


def test_video_download_preserves_cached_normal_post(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "input/creator/123"
    source.mkdir(parents=True)
    (source / "meta.json").write_text(
        json.dumps(
            {
                "post_id": "123",
                "is_slideshow": False,
                "created_at": "2026-10-09T00:00:00Z",
                "views": 100,
                "saves": 2,
                "shares": 1,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output/creator/123"
    output.mkdir(parents=True)
    cached = output / "video.mp4"
    cached.write_bytes(b"cached-video")
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(download_videos, "ffprobe", lambda path: {})
    monkeypatch.setattr(
        "sys.argv",
        [
            "download-videos",
            str(tmp_path / "input"),
            "--out",
            str(tmp_path / "output"),
        ],
    )
    main()
    assert cached.read_bytes() == b"cached-video"
    manifest = json.loads((output / "source_meta.json").read_text())["manifest"]
    assert manifest["download_method"] == "cached"
    assert manifest["video_path"] == "output/creator/123/video.mp4"


def test_forced_download_failure_preserves_last_complete_video(tmp_path, monkeypatch):
    output = tmp_path / "output/creator/123"
    output.mkdir(parents=True)
    cached = output / "video.mp4"
    cached.write_bytes(b"last-complete-video")
    monkeypatch.setattr(
        download_videos,
        "discover",
        lambda root: [{"account": "creator", "post_id": "123", "url": "synthetic", "_raw": {}}],
    )
    monkeypatch.setattr(download_videos, "download_ytdlp", lambda *args: (None, "failed"))
    monkeypatch.setattr(download_videos, "download_direct", lambda *args: (None, "failed"))
    monkeypatch.setattr(
        "sys.argv",
        ["download-videos", str(tmp_path / "input"), "--out", str(output.parent.parent), "--force"],
    )
    main()
    assert cached.read_bytes() == b"last-complete-video"
    report = json.loads((output.parent.parent / "report.json").read_text())
    assert report["failed"] == 1 and report["downloaded_or_cached"] == 0
