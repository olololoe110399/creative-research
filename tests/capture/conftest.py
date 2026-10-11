from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from creative_research.capture import media, scrape, videos


@pytest.fixture
def capture(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("APIFY_TOKEN", "synthetic-private-token")
    accounts = tmp_path / "accounts.txt"
    accounts.write_text("# sample\n@creator\nhttps://www.tiktok.com/@CREATOR\nother\n")
    posts = [
        {
            "id": "7649340799209065748",
            "input": "creator",
            "isSlideshow": True,
            "slideshowImageLinks": [
                {"tiktokLink": "https://example.test/slide1"},
                {"tiktokLink": "https://example.test/slide2"},
            ],
            "authorMeta": {
                "name": "creator",
                "originalAvatarUrl": "https://example.test/avatar",
                "id": "author1",
            },
            "videoMeta": {"originalCoverUrl": "https://example.test/cover"},
            "hashtags": ["example", {"name": "tag"}],
            "playCount": 0,
            "text": "Tiếng Việt 日本語",
        },
        {
            "id": "7649340799209065749",
            "input": "creator",
            "isSlideshow": False,
            "webVideoUrl": "https://www.tiktok.com/@creator/video/7649340799209065749",
            "videoMeta": {"originalCoverUrl": "https://example.test/video-cover"},
            "playCount": 42,
        },
    ]
    calls = []

    class Client:
        def __init__(self, token, **kwargs):
            assert token == "synthetic-private-token"
            assert kwargs["timeout_medium"].total_seconds() > 0

        def actor(self, name):
            def call(**kwargs):
                calls.append(kwargs["run_input"])
                return {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}

            return SimpleNamespace(start=call)

        def run(self, run_id):
            return SimpleNamespace(
                wait_for_finish=lambda **kwargs: {
                    "id": run_id,
                    "status": "SUCCEEDED",
                    "defaultDatasetId": "dataset-1",
                }
            )

        def dataset(self, dataset_id):
            return SimpleNamespace(iterate_items=lambda **kwargs: iter(posts))

    monkeypatch.setattr(scrape, "ApifyClient", Client)
    actual_client = httpx.AsyncClient
    requests = []

    def transport(request):
        assert "Authorization" not in request.headers
        requests.append(str(request.url))
        return httpx.Response(200, content=b"synthetic-image")

    monkeypatch.setattr(
        media.httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    monkeypatch.setattr(videos, "ffprobe", lambda path: {})

    def video(url, out, browser, cookies):
        target = out / "video.mp4"
        target.write_bytes(b"synthetic-video" * 2000)
        return target, None

    monkeypatch.setattr(videos, "download_ytdlp", video)
    args = [
        "scrape",
        "--accounts-file",
        str(accounts),
        "--out",
        "data/raw/run-001",
        "--max-posts",
        "2",
        "--max-charge-usd",
        "0.5",
    ]
    return tmp_path, args, posts, calls, requests
