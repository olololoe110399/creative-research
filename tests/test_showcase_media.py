from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creative_research.stages.export_showcase import export_showcase


def test_showcase_thumbnail_media_is_opt_in_and_anonymized(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    source = tmp_path / "data/02_media/tiktok/real_creator/123"
    source.mkdir(parents=True)
    (source / "cover.jpg").write_bytes(b"fake-jpg")

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
        media_mode="thumbnails",
        media_limit=10,
    )

    posts = json.loads((out / "posts.json").read_text(encoding="utf-8"))
    assert posts[0]["thumbnail_path"] == "assets/thumbnails/post-0001.jpg"
    assert (out / posts[0]["thumbnail_path"]).read_bytes() == b"fake-jpg"
    assert "real_creator" not in posts[0]["thumbnail_path"]
    assert "123" not in posts[0]["thumbnail_path"]
    assert manifest["media_mode"] == "thumbnails"
    assert manifest["share_safe_defaults"] is False
    assert manifest["media_posts_selected"] == 1


def test_showcase_preview_mode_copies_video_for_selected_video(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", str(tmp_path))

    cover = tmp_path / "data/02_media/tiktok/creator/999"
    cover.mkdir(parents=True)
    (cover / "cover.jpg").write_bytes(b"poster")

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
        media_mode="previews",
        media_limit=10,
    )

    posts = json.loads((out / "posts.json").read_text(encoding="utf-8"))
    post = posts[0]
    assert post["thumbnail_path"] == "assets/thumbnails/post-0001.jpg"
    assert post["video_path"] == "assets/videos/post-0001.mp4"
    assert (out / post["video_path"]).read_bytes() == b"video-bytes"


def test_showcase_media_limit_selects_highest_ranked_posts(
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
        (source / "cover.jpg").write_bytes(f"cover-{i}".encode())
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
        media_mode="thumbnails",
        media_limit=1,
    )

    posts = json.loads((out / "posts.json").read_text(encoding="utf-8"))
    with_media = [p for p in posts if "thumbnail_path" in p]
    assert len(with_media) == 1
    assert with_media[0]["account_alias"] == "Creator 02"
