from __future__ import annotations

import csv
import json

import pytest

from creative_research.capture.accounts import _post_identity
from creative_research.cli.commands import select_accounts
from creative_research.identity import clean_account_handle
from creative_research.infrastructure.storage import read_jsonl, write_jsonl


def test_clean_username_accepts_url_and_at_handle() -> None:
    assert (
        clean_account_handle("https://www.tiktok.com/@SyntheticCreator12/video/123")
        == "SyntheticCreator12"
    )
    assert clean_account_handle("@synthetic_beta") == "synthetic_beta"


def test_pid_prefers_post_id() -> None:
    assert _post_identity({"post_id": 123, "url": "fallback"}) == "123"


def test_merge_preserves_latest_snapshot_and_normalized_csv_contract(tmp_path, monkeypatch):
    first, latest = tmp_path / "first", tmp_path / "latest"
    write_jsonl(
        first / "normalized/posts.jsonl",
        [{"account": "creator", "post_id": "1", "views": 10, "labels": ["old"]}],
    )
    write_jsonl(
        first / "posts/creator.jsonl",
        [{"authorMeta": {"name": "creator"}, "id": "1", "source": "account"}],
    )
    write_jsonl(first / "raw/all_items.jsonl", [{"input": "@creator", "id": "1", "source": "raw"}])
    write_jsonl(
        latest / "normalized/posts.jsonl",
        [
            {"account": "CREATOR", "post_id": "1", "views": 20, "labels": ["new"]},
            {"account": "other", "post_id": "2"},
        ],
    )
    write_jsonl(
        latest / "raw/all_items.jsonl",
        [{"author": {"uniqueId": "Creator"}, "id": "1", "source": "latest"}],
    )
    output = tmp_path / "selected"
    monkeypatch.setattr(
        "sys.argv",
        [
            "select-accounts",
            "--sources",
            str(first),
            str(latest),
            "--accounts",
            "@Creator",
            "--out",
            str(output),
        ],
    )
    select_accounts.main()
    records = read_jsonl(output / "normalized/posts.jsonl")
    assert records == [{"account": "CREATOR", "post_id": "1", "views": 20, "labels": ["new"]}]
    assert read_jsonl(output / "posts/Creator.jsonl")[0]["source"] == "latest"
    with (output / "normalized/posts.csv").open(encoding="utf-8-sig") as stream:
        csv_row = next(csv.DictReader(stream))
    assert csv_row["views"] == "20" and json.loads(csv_row["labels"]) == ["new"]
    assert json.loads((output / "manifest.json").read_text())["accounts"] == {
        "Creator": {"raw_posts": 1, "normalized_posts": 1}
    }


@pytest.mark.parametrize("handle", ["../escape", "a\\b", "@"])
def test_account_selection_preflights_all_handles_before_any_output(tmp_path, monkeypatch, handle):
    output = tmp_path / "selected"
    monkeypatch.setattr(
        "sys.argv",
        [
            "select-accounts",
            "--sources",
            str(tmp_path / "source"),
            "--accounts",
            "valid",
            handle,
            "--out",
            str(output),
        ],
    )
    with pytest.raises(ValueError):
        select_accounts.main()
    assert not output.exists()


def test_account_selection_rejects_symlink_escape_before_writes(tmp_path, monkeypatch):
    output, external = tmp_path / "selected", tmp_path / "external"
    output.mkdir()
    external.mkdir()
    (output / "normalized").symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(
        "sys.argv",
        [
            "select-accounts",
            "--sources",
            str(tmp_path / "source"),
            "--accounts",
            "creator",
            "--out",
            str(output),
        ],
    )
    with pytest.raises(ValueError, match="path_outside_output"):
        select_accounts.main()
    assert not list(external.iterdir())
    assert not (output / "posts").exists()
