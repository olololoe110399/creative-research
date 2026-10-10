from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from creative_research.capture import scrape
from creative_research.cli.commands.scrape import build_parser, main


def test_actor_adapter_uses_typed_sdk_timeout_and_decimal_budget(monkeypatch) -> None:
    args = build_parser().parse_args(
        ["accounts.txt", "--actor-timeout", "42", "--max-charge-usd", "1.25"]
    )
    seen = {}

    class Actor:
        def call(self, **kwargs):
            seen.update(kwargs)
            return {"id": "synthetic-run", "status": "SUCCEEDED"}

    client = SimpleNamespace(actor=lambda name: Actor())
    assert (
        scrape.run_actor_batch(client, ["synthetic"], scrape.ScrapeOptions(**vars(args)), None)[
            "id"
        ]
        == "synthetic-run"
    )
    assert seen["run_timeout"] == timedelta(seconds=42)
    assert seen["max_total_charge_usd"] == Decimal("1.25")
    assert seen["run_input"]["profiles"] == ["synthetic"]


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
    monkeypatch.setattr("sys.argv", ["scrape", str(tmp_path / "missing-accounts.txt"), *options])
    monkeypatch.setattr(
        scrape, "ApifyClient", lambda *a, **k: pytest.fail("Provider must not be called")
    )
    with pytest.raises(ValueError, match="must be"):
        main()
    assert list(tmp_path.iterdir()) == []
