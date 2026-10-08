from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

from creative_research.stages.intelligence import _make_handler


def test_lab_streams_local_thumbnail_and_video_ranges(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CREATIVE_RESEARCH_PROJECT_ROOT",
        str(tmp_path),
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    archive = tmp_path / "data/02_media/tiktok/creator/1"
    archive.mkdir(parents=True)
    (archive / "cover.jpg").write_bytes(b"thumbnail-bytes")

    video_dir = tmp_path / "data/03_video_media/creator/1"
    video_dir.mkdir(parents=True)
    video_bytes = b"0123456789abcdef"
    (video_dir / "video.mp4").write_bytes(video_bytes)

    record = {
        "post_uid": "P1",
        "account": "creator",
        "post_id": "1",
        "content_type": "video",
        "source_media_path": "data/03_video_media/creator/1",
    }
    handler = _make_handler(
        root=workspace,
        reviews_path=tmp_path / "reviews.toml",
        read_only=True,
        media_records={"P1": record},
    )

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()
    try:
        port = int(server.server_address[1])
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/media/thumbnail/P1"
        ) as response:
            assert response.status == 200
            assert response.read() == b"thumbnail-bytes"

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/media/video/P1",
            headers={"Range": "bytes=2-5"},
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == (
                f"bytes 2-5/{len(video_bytes)}"
            )
            assert response.read() == video_bytes[2:6]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
