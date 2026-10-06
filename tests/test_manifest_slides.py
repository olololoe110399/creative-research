from __future__ import annotations

import json
from pathlib import Path

from creative_research.stages.manifest_slides import discover_slideshows


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_discover_slideshows_filters_video_and_uses_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "data/02_media/tiktok"

    slide_post = root / "acct" / "111"
    slide_post.mkdir(parents=True)
    _write_json(
        slide_post / "meta.json",
        {
            "post_id": "111",
            "is_slideshow": True,
            "views": 100,
            "saves": 10,
            "shares": 5,
            "created_at": "2026-01-01T00:00:00Z",
        },
    )
    (slide_post / "slide_001.jpg").write_bytes(b"a")
    (slide_post / "slide_002.jpg").write_bytes(b"b")

    video_post = root / "acct" / "222"
    video_post.mkdir(parents=True)
    _write_json(video_post / "meta.json", {"post_id": "222", "is_slideshow": False})

    df = discover_slideshows(root, path_base=tmp_path)
    assert list(df["post_id"]) == ["111"]
    assert df.iloc[0]["slide_count"] == 2
    assert df.iloc[0]["post_dir"] == "data/02_media/tiktok/acct/111"
    assert df.iloc[0]["save_rate"] == 0.1
