from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.stages.export_showcase import export_showcase


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_remote_mode_exports_scraped_urls_without_copying_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    source = tmp_path / "data/02_media/tiktok/real_creator/123"
    source.mkdir(parents=True)
    _write_json(
        source / "meta.json",
        {
            "url": "https://www.tiktok.com/@real_creator/photo/123",
            "cover_original_url": "https://cdn.example/cover.jpg",
        },
    )
    _write_json(
        source / "raw.json",
        {
            "webVideoUrl": "https://www.tiktok.com/@real_creator/photo/123",
            "slideshowImageLinks": [
                {
                    "tiktokLink": "https://cdn.example/slide-1.jpeg",
                    "downloadLink": "https://apify.example/slide-1",
                },
                {
                    "tiktokLink": "https://cdn.example/slide-2.jpeg",
                    "downloadLink": "https://apify.example/slide-2",
                },
            ],
        },
    )

    master = pd.DataFrame(
        [
            {
                "account": "real_creator",
                "post_id": "123",
                "content_type": "slideshow",
                "created_at": "2026-01-01T00:00:00Z",
                "views": 1000,
                "global_views_pct": 0.99,
            }
        ]
    )

    out = tmp_path / "showcase"
    manifest = export_showcase(
        master,
        out,
        media_mode="remote",
        media_limit=10,
    )

    posts = json.loads((out / "posts.json").read_text(encoding="utf-8"))
    post = posts[0]
    assert post["post_url"] == "https://www.tiktok.com/@real_creator/photo/123"
    assert post["thumbnail_url"] == "https://cdn.example/slide-1.jpeg"
    assert post["slide_urls"] == [
        "https://cdn.example/slide-1.jpeg",
        "https://cdn.example/slide-2.jpeg",
    ]
    assert "thumbnail_path" not in post
    assert not (out / "assets").exists()
    assert manifest["media_mode"] == "remote"
    assert manifest["share_safe_defaults"] is False


def test_remote_video_mode_exports_direct_video_and_cover_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    source = tmp_path / "data/02_media/tiktok/creator/999"
    source.mkdir(parents=True)
    _write_json(
        source / "meta.json",
        {
            "url": "https://www.tiktok.com/@creator/video/999",
            "cover_original_url": "https://cdn.example/video-cover.jpeg",
        },
    )
    _write_json(
        source / "raw.json",
        {
            "webVideoUrl": "https://www.tiktok.com/@creator/video/999",
            "videoMeta": {
                "originalCoverUrl": "https://cdn.example/video-cover.jpeg",
                "playAddr": "https://video.example/video/tos/abc?mime_type=video",
                "downloadAddr": "https://video.example/video/tos/backup?mime_type=video",
            },
        },
    )

    master = pd.DataFrame(
        [
            {
                "account": "creator",
                "post_id": "999",
                "content_type": "video",
                "created_at": "2026-01-01T00:00:00Z",
                "views": 1000,
                "global_views_pct": 0.99,
            }
        ]
    )

    out = tmp_path / "showcase"
    export_showcase(
        master,
        out,
        media_mode="remote",
        media_limit=10,
    )

    post = json.loads((out / "posts.json").read_text(encoding="utf-8"))[0]
    assert post["thumbnail_url"] == "https://cdn.example/video-cover.jpeg"
    assert post["video_url"] == "https://video.example/video/tos/abc?mime_type=video"
    assert post["video_fallback_urls"] == [
        "https://video.example/video/tos/backup?mime_type=video"
    ]


def test_hybrid_mode_exports_remote_urls_plus_local_fallbacks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    archive = tmp_path / "data/02_media/tiktok/creator/999"
    archive.mkdir(parents=True)
    (archive / "cover.jpg").write_bytes(b"poster")
    _write_json(
        archive / "meta.json",
        {
            "url": "https://www.tiktok.com/@creator/video/999",
            "cover_original_url": "https://cdn.example/cover.jpeg",
        },
    )
    _write_json(
        archive / "raw.json",
        {
            "videoMeta": {
                "originalCoverUrl": "https://cdn.example/cover.jpeg",
                "playAddr": "https://video.example/video/tos/live?mime_type=video",
            }
        },
    )

    video_dir = tmp_path / "data/03_video_media/creator/999"
    video_dir.mkdir(parents=True)
    (video_dir / "video.mp4").write_bytes(b"video-bytes")

    master = pd.DataFrame(
        [
            {
                "account": "creator",
                "post_id": "999",
                "content_type": "video",
                "created_at": "2026-01-01T00:00:00Z",
                "views": 1000,
                "global_views_pct": 0.99,
                "source_media_path": "data/03_video_media/creator/999",
            }
        ]
    )

    out = tmp_path / "showcase"
    export_showcase(
        master,
        out,
        media_mode="hybrid",
        media_limit=10,
    )

    post = json.loads((out / "posts.json").read_text(encoding="utf-8"))[0]
    assert post["post_url"] == "https://www.tiktok.com/@creator/video/999"
    assert post["thumbnail_url"] == "https://cdn.example/cover.jpeg"
    assert post["video_url"] == "https://video.example/video/tos/live?mime_type=video"
    assert post["thumbnail_path"] == "assets/thumbnails/post-0001.jpg"
    assert post["video_path"] == "assets/videos/post-0001.mp4"
    assert (out / post["thumbnail_path"]).read_bytes() == b"poster"
    assert (out / post["video_path"]).read_bytes() == b"video-bytes"


def test_copy_mode_keeps_post_url_but_omits_remote_media_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    source = tmp_path / "data/02_media/tiktok/creator/123"
    source.mkdir(parents=True)
    (source / "cover.jpg").write_bytes(b"cover")
    _write_json(
        source / "meta.json",
        {
            "url": "https://www.tiktok.com/@creator/photo/123",
            "cover_original_url": "https://cdn.example/cover.jpeg",
        },
    )
    _write_json(
        source / "raw.json",
        {
            "slideshowImageLinks": [
                {"tiktokLink": "https://cdn.example/slide-1.jpeg"}
            ]
        },
    )

    master = pd.DataFrame(
        [
            {
                "account": "creator",
                "post_id": "123",
                "content_type": "slideshow",
                "created_at": "2026-01-01T00:00:00Z",
                "views": 100,
                "global_views_pct": 0.7,
            }
        ]
    )

    out = tmp_path / "showcase"
    export_showcase(
        master,
        out,
        media_mode="copy",
        media_limit=10,
    )

    post = json.loads((out / "posts.json").read_text(encoding="utf-8"))[0]
    assert post["post_url"] == "https://www.tiktok.com/@creator/photo/123"
    assert post["thumbnail_path"] == "assets/thumbnails/post-0001.jpg"
    assert "thumbnail_url" not in post
    assert "slide_urls" not in post


def test_media_limit_selects_highest_ranked_posts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    rows = []
    for i, pct in enumerate([0.2, 0.9, 0.5], start=1):
        account = f"creator{i}"
        post_id = str(i)
        source = tmp_path / "data/02_media/tiktok" / account / post_id
        source.mkdir(parents=True)
        _write_json(
            source / "meta.json",
            {
                "url": f"https://www.tiktok.com/@{account}/photo/{post_id}",
                "cover_original_url": f"https://cdn.example/{i}.jpg",
            },
        )
        _write_json(source / "raw.json", {})
        rows.append(
            {
                "account": account,
                "post_id": post_id,
                "content_type": "slideshow",
                "created_at": f"2026-01-0{i}T00:00:00Z",
                "views": i * 100,
                "global_views_pct": pct,
            }
        )

    out = tmp_path / "showcase"
    export_showcase(
        pd.DataFrame(rows),
        out,
        media_mode="remote",
        media_limit=1,
    )

    posts = json.loads((out / "posts.json").read_text(encoding="utf-8"))
    with_media = [p for p in posts if "post_url" in p]
    assert len(with_media) == 1
    assert with_media[0]["account_alias"] == "Creator 02"
