from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from creative_research.capture.media import MediaArchiveOptions, archive_media, fetch_candidate
from creative_research.cli.commands.prepare_media import build_parser


@pytest.mark.parametrize("post_id", ["../../escape", None, "..", "a\\b"])
def test_prepare_media_rejects_unsafe_ids_before_writing_metadata(
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
    args = build_parser().parse_args(
        [
            str(posts.parent),
            "--out",
            str(output),
            "--dry-run",
        ]
    )
    with pytest.raises(ValueError, match="unsafe_path_component"):
        asyncio.run(archive_media(MediaArchiveOptions(**vars(args))))
    assert not list(output.rglob("raw.json"))
    assert not list(output.rglob("meta.json"))


def test_prepare_media_rejects_output_symlink_escape(tmp_path: Path) -> None:
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
    args = build_parser().parse_args(
        [
            str(posts.parent),
            "--out",
            str(output),
            "--dry-run",
        ]
    )
    with pytest.raises(ValueError, match="path_outside_output"):
        asyncio.run(archive_media(MediaArchiveOptions(**vars(args))))
    assert not list(outside.iterdir())


def test_prepare_media_dry_run_keeps_normal_post_layout(tmp_path: Path) -> None:
    posts = tmp_path / "input/posts"
    posts.mkdir(parents=True)
    (posts / "creator.jsonl").write_text(
        json.dumps({"id": "123", "input": "creator", "isSlideshow": True}),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    args = build_parser().parse_args(
        [
            str(posts.parent),
            "--out",
            str(output),
            "--dry-run",
        ]
    )
    asyncio.run(archive_media(MediaArchiveOptions(**vars(args))))
    assert json.loads((output / "creator/123/meta.json").read_text())["post_id"] == "123"


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
