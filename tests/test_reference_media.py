from __future__ import annotations

import json
from pathlib import Path

from creative_research.reference_media import export_media_for_post, preview_media_for_post, select_media_keys


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_remote_mode_reads_archived_slideshow_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    source = tmp_path / "data/02_media/tiktok/creator/123"
    source.mkdir(parents=True)
    _write_json(source / "meta.json", {"url": "https://www.tiktok.com/@creator/photo/123"})
    _write_json(
        source / "raw.json",
        {
            "slideshowImageLinks": [
                {"tiktokLink": "https://cdn.example/slide-1.jpeg"},
                {"tiktokLink": "https://cdn.example/slide-2.jpeg"},
            ]
        },
    )
    result = export_media_for_post(
        {"account": "creator", "post_id": "123", "content_type": "slideshow"},
        "REF-0001",
        tmp_path / "pack",
        mode="remote",
    )
    assert result["post_url"] == "https://www.tiktok.com/@creator/photo/123"
    assert result["thumbnail_url"] == "https://cdn.example/slide-1.jpeg"
    assert result["slide_urls"] == [
        "https://cdn.example/slide-1.jpeg",
        "https://cdn.example/slide-2.jpeg",
    ]


def test_hybrid_mode_combines_remote_and_local_video(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    archive = tmp_path / "data/02_media/tiktok/creator/999"
    archive.mkdir(parents=True)
    (archive / "cover.jpg").write_bytes(b"poster")
    _write_json(archive / "meta.json", {"url": "https://www.tiktok.com/@creator/video/999"})
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
    (video_dir / "video.mp4").write_bytes(b"video")

    result = export_media_for_post(
        {
            "account": "creator",
            "post_id": "999",
            "content_type": "video",
            "source_media_path": "data/03_video_media/creator/999",
        },
        "REF-0002",
        tmp_path / "pack",
        mode="hybrid",
    )
    assert result["video_url"] == "https://video.example/video/tos/live?mime_type=video"
    assert result["thumbnail_path"] == "assets/thumbnails/ref-0002.jpg"
    assert result["video_path"] == "assets/videos/ref-0002.mp4"


def test_copy_mode_keeps_original_link_without_remote_media(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    source = tmp_path / "data/02_media/tiktok/creator/123"
    source.mkdir(parents=True)
    (source / "cover.jpg").write_bytes(b"cover")
    _write_json(source / "meta.json", {"url": "https://www.tiktok.com/@creator/photo/123"})
    _write_json(
        source / "raw.json",
        {"slideshowImageLinks": [{"tiktokLink": "https://cdn.example/slide.jpeg"}]},
    )
    result = export_media_for_post(
        {"account": "creator", "post_id": "123", "content_type": "slideshow"},
        "REF-0003",
        tmp_path / "pack",
        mode="copy",
    )
    assert result["post_url"] == "https://www.tiktok.com/@creator/photo/123"
    assert result["thumbnail_path"] == "assets/thumbnails/ref-0003.jpg"
    assert "thumbnail_url" not in result
    assert "slide_urls" not in result


def test_media_key_selector_can_limit_payload() -> None:
    records = [
        {"account": "a", "post_id": "1", "global_views_pct": 0.2, "views": 100},
        {"account": "b", "post_id": "2", "global_views_pct": 0.9, "views": 200},
        {"account": "c", "post_id": "3", "global_views_pct": 0.5, "views": 300},
    ]
    assert select_media_keys(records, limit=1) == {("b", "2")}


def test_preview_media_returns_only_lightweight_remote_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))
    source = tmp_path / "data/02_media/tiktok/creator/321"
    source.mkdir(parents=True)
    _write_json(
        source / "meta.json",
        {"url": "https://www.tiktok.com/@creator/photo/321"},
    )
    _write_json(
        source / "raw.json",
        {
            "slideshowImageLinks": [
                {"tiktokLink": "https://cdn.example/slide-1.jpeg"},
                {"tiktokLink": "https://cdn.example/slide-2.jpeg"},
            ]
        },
    )
    preview = preview_media_for_post(
        {"account": "creator", "post_id": "321", "content_type": "slideshow"}
    )
    assert preview == {
        "post_url": "https://www.tiktok.com/@creator/photo/321",
        "thumbnail_url": "https://cdn.example/slide-1.jpeg",
    }
