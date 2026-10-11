from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from creative_research.capture import scrape
from creative_research.cli.commands.scrape import build_parser, main
from creative_research.identity import clean_account_handle


def test_clean_username_accepts_url_and_at_handle() -> None:
    assert (
        clean_account_handle("https://www.tiktok.com/@SyntheticCreator12/video/123")
        == "SyntheticCreator12"
    )
    assert clean_account_handle("@synthetic_beta") == "synthetic_beta"


def test_actor_adapter_uses_typed_sdk_timeout_and_decimal_budget(monkeypatch) -> None:
    args = build_parser().parse_args(
        ["--accounts-file", "accounts.txt", "--actor-timeout", "42", "--max-charge-usd", "1.25"]
    )
    seen = {}

    class Actor:
        def start(self, **kwargs):
            seen.update(kwargs)
            return {"id": "synthetic-run", "status": "SUCCEEDED"}

    client = SimpleNamespace(
        actor=lambda name: Actor(),
        run=lambda run_id: SimpleNamespace(
            wait_for_finish=lambda **kwargs: {"id": run_id, "status": "SUCCEEDED"}
        ),
    )
    assert (
        scrape.run_actor_batch(client, ["synthetic"], scrape.ScrapeOptions(**vars(args)))["id"]
        == "synthetic-run"
    )
    assert seen["run_timeout"] == timedelta(seconds=42)
    assert seen["max_total_charge_usd"] == Decimal("1.25")
    assert seen["run_input"]["profiles"] == ["synthetic"]
    for key in (
        "shouldDownloadVideos",
        "shouldDownloadCovers",
        "shouldDownloadSlideshowImages",
        "shouldDownloadAvatars",
    ):
        assert seen["run_input"][key] is False
    assert seen["run_input"]["downloadSubtitlesOptions"] == "NEVER_DOWNLOAD_SUBTITLES"
    assert "videoKvStoreIdOrName" not in seen["run_input"]


@pytest.mark.parametrize(
    "options",
    [
        ["--actor-timeout", "0"],
        ["--max-posts", "0"],
        ["--max-charge-usd", "nan"],
        ["--max-charge-usd", "-1"],
        ["--max-charge-usd", "inf"],
    ],
)
def test_invalid_scrape_budgets_fail_before_reading_evidence_or_calling_provider(
    tmp_path, monkeypatch, options
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["scrape", "--accounts-file", str(tmp_path / "missing-accounts.txt"), *options]
    )
    monkeypatch.setattr(
        scrape, "ApifyClient", lambda *a, **k: pytest.fail("Provider must not be called")
    )
    with pytest.raises(ValueError, match="must be"):
        main()
    assert list(tmp_path.iterdir()) == []


def test_rebuilding_capture_removes_stale_derived_records_and_preserves_raw_batches(tmp_path):
    from creative_research.infrastructure.storage import read_jsonl, write_jsonl

    original = {"id": "1", "input": "old", "authorMeta": {"name": "old"}}
    replacement = {"id": "2", "input": "new", "authorMeta": {"name": "new"}}
    write_jsonl(tmp_path / "raw/batches/batch_001_items.jsonl", [original])
    scrape.split_and_write([original], tmp_path)
    rows, counts = scrape.split_and_write([replacement], tmp_path)
    assert counts == {"new": 1} and len(rows) == 1
    assert not (tmp_path / "posts/old.jsonl").exists()
    assert not (tmp_path / "profiles/old.json").exists()
    assert read_jsonl(tmp_path / "posts/new.jsonl") == [replacement]
    assert read_jsonl(tmp_path / "raw/batches/batch_001_items.jsonl") == [original]
    scrape.split_and_write([], tmp_path)
    assert not list((tmp_path / "posts").glob("*.jsonl"))
    assert not list((tmp_path / "profiles").glob("*.json"))


def test_invalid_recovery_option_leaves_new_capture_directory_unwritten(tmp_path, monkeypatch):
    account_file = tmp_path / "accounts.txt"
    account_file.write_text("creator\n")
    monkeypatch.setenv("APIFY_TOKEN", "synthetic-private-token")
    args = build_parser().parse_args(
        [
            "--accounts-file",
            str(account_file),
            "--out",
            str(tmp_path / "new-capture"),
            "--recover-run",
            "1=run-1",
        ]
    )
    with pytest.raises(ValueError, match="requires --resume"):
        scrape.archive_posts(scrape.ScrapeOptions(**vars(args)))
    assert not (tmp_path / "new-capture").exists()
