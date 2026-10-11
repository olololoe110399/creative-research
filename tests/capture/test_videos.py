from __future__ import annotations

import json
from pathlib import Path

import pytest

from creative_research.capture import videos as download_videos


def options(source: Path, out: Path):
    return download_videos.VideoDownloadOptions(
        input=str(source),
        out=str(out),
        cookies_from_browser=None,
        cookies_file=None,
    )


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
    with pytest.raises(ValueError, match="unsafe_path_component"):
        download_videos.download_videos(options(tmp_path / "input", output))
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
    from creative_research.capture.cache import attest, fingerprint

    attest(cached, fingerprint({"raw": {}, "meta": json.loads((source / "meta.json").read_text())}))
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(download_videos, "ffprobe", lambda path: {})
    download_videos.download_videos(options(tmp_path / "input", tmp_path / "output"))
    assert cached.read_bytes() == b"cached-video"
    manifest = json.loads((output / "source_meta.json").read_text())["manifest"]
    assert manifest["download_method"] == "cached"
    assert manifest["video_path"] == "output/creator/123/video.mp4"


def test_unattested_video_refresh_failure_preserves_last_complete_bytes(tmp_path, monkeypatch):
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
    download_videos.download_videos(options(tmp_path / "input", output.parent.parent))
    assert cached.read_bytes() == b"last-complete-video"
    report = json.loads((output.parent.parent / "video_report.json").read_text())
    assert report["failed"] == 1 and report["downloaded_or_cached"] == 0


@pytest.mark.parametrize("post_url", [None, "https://www.tiktok.com/@creator/video/123"])
def test_direct_fallback_skips_bad_responses_and_reuses_verified_bytes(
    tmp_path, monkeypatch, post_url
):
    import io

    source = tmp_path / "input/creator/123"
    source.mkdir(parents=True)
    urls = [f"https://example.test/{name}" for name in ("expired", "unavailable", "video")]
    raw = {
        "id": "123",
        "isSlideshow": False,
        "webVideoUrl": post_url,
        "videoMeta": {
            "downloadAddresses": [
                *urls,
                urls[-1],
                "https://example.test/cover.jpg",
                post_url or "https://www.tiktok.com/@creator",
            ]
        },
    }
    (source / "raw.json").write_text(json.dumps(raw))
    (source.parent / "empty").mkdir()
    primary = []

    def ytdlp(*args):
        primary.append(args[0])
        return None, "source unavailable"

    class Response(io.BytesIO):
        def __init__(self, body, content_type):
            super().__init__(body)
            self.headers = {"Content-Type": content_type}

    attempts = []

    def request(req, **kwargs):
        attempts.append(req.full_url)
        assert kwargs["timeout"] > 0
        if req.full_url == urls[0]:
            return Response(b"expired", "text/html")
        if req.full_url == urls[1]:
            raise TimeoutError("synthetic timeout")
        assert req.full_url == urls[2]
        return Response(b"complete-video" * 2000, "video/x-synthetic")

    monkeypatch.setattr(download_videos, "download_ytdlp", ytdlp)
    monkeypatch.setattr(download_videos.urllib.request, "urlopen", request)
    monkeypatch.setattr(download_videos, "ffprobe", lambda path: {})
    output = tmp_path / "output"
    args = options(source.parent.parent, output)
    report = download_videos.download_videos(args)
    assert report["failed"] == 0 and report["downloaded_or_cached"] == 1
    assert attempts == urls
    assert primary == ([post_url] if post_url else [])
    manifest = json.loads((output / "creator/123/source_meta.json").read_text())["manifest"]
    assert manifest["download_method"] == "direct_raw_url"
    assert (output / "creator/123/video.mp4").read_bytes() == b"complete-video" * 2000

    monkeypatch.setattr(
        download_videos, "download_ytdlp", lambda *a: pytest.fail("Verified cache must be reused")
    )
    monkeypatch.setattr(
        download_videos.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("Verified cache must be reused"),
    )
    assert download_videos.download_videos(args)["failed"] == 0
    manifest = json.loads((output / "creator/123/source_meta.json").read_text())["manifest"]
    assert manifest["download_method"] == "cached"


@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError])
def test_ytdlp_os_failure_returns_safe_diagnostic_and_preserves_old_video(
    tmp_path, monkeypatch, error
):
    old = tmp_path / "video.mp4"
    old.write_bytes(b"last-complete-video")
    monkeypatch.setenv("APIFY_TOKEN", "synthetic-private-token")

    def fail(*args, **kwargs):
        raise error("Cannot execute: synthetic-private-token")

    monkeypatch.setattr(download_videos.subprocess, "run", fail)
    video, diagnostic = download_videos.download_ytdlp(
        "https://example.test/post", tmp_path, None, None
    )
    assert video is None and "Cannot run yt-dlp" in diagnostic
    assert "synthetic-private-token" not in diagnostic
    assert old.read_bytes() == b"last-complete-video"
    assert list(tmp_path.iterdir()) == [old]
