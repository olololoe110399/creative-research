from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from creative_research.capture.media import MediaArchiveOptions, archive_media, fetch_candidate
from creative_research.cli.commands.download_media import build_parser as download_parser


def options(argv):
    values = vars(download_parser().parse_args(["--input", *argv]))
    for key in ("json", "no_videos", "cookies_from_browser", "cookies_file"):
        values.pop(key)
    return MediaArchiveOptions(**values)


@pytest.mark.parametrize("post_id", ["../../escape", None, "..", "a\\b"])
def test_media_archive_rejects_unsafe_ids_before_writing_metadata(
    tmp_path: Path,
    post_id: str | None,
) -> None:
    post_id = post_id if post_id is not None else str(tmp_path / "escape")
    posts = tmp_path / "input/posts"
    posts.mkdir(parents=True)
    rows = [{"id": "123", "input": "creator"}, {"id": post_id, "input": "creator"}]
    (posts / "creator.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    args = options(
        [
            str(posts.parent),
            "--out",
            str(output),
            "--dry-run",
        ]
    )
    with pytest.raises(ValueError, match="unsafe_path_component"):
        asyncio.run(archive_media(args))
    assert not list(output.rglob("raw.json"))
    assert not list(output.rglob("meta.json"))


def test_media_archive_rejects_output_symlink_escape(tmp_path: Path) -> None:
    posts = tmp_path / "input/posts"
    posts.mkdir(parents=True)
    (posts / "creator.jsonl").write_text(
        json.dumps({"id": "123", "input": "creator"}),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "creator").symlink_to(outside, target_is_directory=True)
    args = options(
        [
            str(posts.parent),
            "--out",
            str(output),
            "--dry-run",
        ]
    )
    with pytest.raises(ValueError, match="path_outside_output"):
        asyncio.run(archive_media(args))
    assert not list(outside.iterdir())


def test_media_archive_dry_run_keeps_normal_post_layout(tmp_path: Path) -> None:
    posts = tmp_path / "input/posts"
    posts.mkdir(parents=True)
    (posts / "creator.jsonl").write_text(
        json.dumps({"id": "123", "input": "creator", "isSlideshow": True}),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    args = options(
        [
            str(posts.parent),
            "--out",
            str(output),
            "--dry-run",
        ]
    )
    asyncio.run(archive_media(args))
    assert not output.exists()


def test_media_archive_plans_a_post_without_id_using_consistent_source_identity(tmp_path):
    source = tmp_path / "input/posts"
    source.mkdir(parents=True)
    (source / "creator.jsonl").write_text(
        json.dumps(
            {
                "input": "creator",
                "videoMeta": {"originalCoverUrl": "https://example.test/cover"},
            }
        )
    )
    output = tmp_path / "output"
    report = asyncio.run(
        archive_media(options([str(source.parent), "--out", str(output), "--dry-run"]))
    )
    assert report["media_jobs_total"] == 1
    assert report["post_keys"][0][0] == "creator"
    assert report["post_keys"][0][1].startswith("sha1_")
    assert not output.exists()


@pytest.mark.parametrize(
    "url,expected_auth",
    [
        ("https://api.apify.com/file", [None, "Bearer synthetic-token"]),
        ("https://apify.com/file", [None, "Bearer synthetic-token"]),
        ("https://cdn.apifyusercontent.com/file", [None, "Bearer synthetic-token"]),
        ("https://evilapify.com/file", [None]),
        ("https://notapifyusercontent.com/file", [None]),
        ("https://apify.com.attacker.invalid/file", [None]),
        ("http://api.apify.com/file", [None]),
        ("https://tiktokcdn.com/file", [None]),
    ],
)
def test_tokens_only_reach_https_apify_domains(url: str, expected_auth: list) -> None:
    observed_auth = []

    def transport(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization")
        observed_auth.append(auth)
        return httpx.Response(200, content=b"image") if auth else httpx.Response(401)

    async def download() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            await fetch_candidate(
                client,
                {"url": url, "source": "fixture"},
                ["synthetic-token"],
                timeout=1,
                retries=0,
            )

    asyncio.run(download())
    assert observed_auth == expected_auth


def test_cross_host_redirect_does_not_forward_apify_token() -> None:
    observed = []

    def transport(request: httpx.Request) -> httpx.Response:
        observed.append((request.url.host, request.headers.get("Authorization")))
        if request.url.host == "attacker.invalid":
            return httpx.Response(200, content=b"image")
        if request.headers.get("Authorization"):
            return httpx.Response(302, headers={"Location": "https://attacker.invalid/file"})
        return httpx.Response(401)

    async def download() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            await fetch_candidate(
                client,
                {"url": "https://api.apify.com/file", "source": "fixture"},
                ["synthetic-token"],
                timeout=1,
                retries=0,
            )

    asyncio.run(download())
    assert observed[-1] == ("attacker.invalid", None)


@pytest.mark.parametrize("content_type", ["text/html; charset=utf-8", "application/json"])
def test_successful_http_error_document_is_never_accepted_as_an_image(content_type):
    async def download():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=b"expired resource", headers={"content-type": content_type}
                )
            )
        ) as client:
            body, log = await fetch_candidate(
                client,
                {"url": "https://example.test/expired", "source": "fixture"},
                [],
                timeout=1,
                retries=0,
            )
            assert body is None
            assert "Unexpected image content-type" in log["attempts"][0]["error"]

    asyncio.run(download())


def test_image_worker_failure_cancels_peers_and_checkpoints_completed_files(tmp_path, monkeypatch):
    from creative_research.capture import media
    from creative_research.infrastructure.storage import read_jsonl, write_jsonl

    source, output = tmp_path / "input", tmp_path / "media"
    write_jsonl(
        source / "posts/creator.jsonl",
        [
            {
                "id": "1",
                "input": "creator",
                "isSlideshow": True,
                "videoMeta": {"originalCoverUrl": "https://example.test/cover"},
                "slideshowImageLinks": [
                    {"tiktokLink": "https://example.test/slide1"},
                    {"tiktokLink": "https://example.test/slide2"},
                ],
            }
        ],
    )

    async def exercise():
        started, cancelled, block = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def worker(client, sem, job, *args):
            if job["kind"] == "cover":
                await started.wait()
                raise OSError("synthetic disk failure")
            if job["index"] == 1:
                job["path"].parent.mkdir(parents=True, exist_ok=True)
                job["path"].write_bytes(b"completed-slide")
                return {"status": "downloaded", "path": str(job["path"])}
            started.set()
            try:
                await block.wait()
                pytest.fail("Peer must be cancelled before archive failure returns")
            finally:
                cancelled.set()

        monkeypatch.setattr(media, "download_one", worker)
        with pytest.raises(OSError, match="disk failure"):
            await archive_media(options([str(source), "--out", str(output)]))
        assert cancelled.is_set()
        rows = read_jsonl(output / "media_manifest.jsonl")
        assert len(rows) == 1 and rows[0]["status"] == "downloaded"
        assert Path(rows[0]["path"]).read_bytes() == b"completed-slide"

    asyncio.run(exercise())
