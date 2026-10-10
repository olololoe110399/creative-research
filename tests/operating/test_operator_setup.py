from __future__ import annotations

import sys
from pathlib import Path

import pytest

from creative_research.capture import scrape
from creative_research.cli.commands.operator_setup import (
    main as setup_main,
)
from creative_research.cli.commands.scrape import main as scrape_main
from creative_research.operating.onboarding import (
    _accounts_file,
    build_operator_registration,
    checked_scrape_operator,
)
from creative_research.operating.registry import load_operator_registry


def _registered(tmp_path: Path, accounts: list[str], *, confirm: bool = True) -> Path:
    path = tmp_path / "operators.toml"
    content = build_operator_registration("OP-TEST", "My research operator", accounts)
    if not confirm:
        content = content.replace("verified = true", "verified = false")
    path.write_text(content, encoding="utf-8")
    return path


def test_setup_generates_private_researcher_assertion_and_url_normalization(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    file = tmp_path / "targets.txt"
    file.write_text(
        "# accounts declared by the researcher\n"
        "https://www.TIKTOK.com/@First.Creator?lang=en\n"
        "@second_creator\n"
        "@SECOND_CREATOR\n",
        encoding="utf-8",
    )
    assert _accounts_file(file) == ["First.Creator", "second_creator"]
    output = tmp_path / "operators.toml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "operator-setup",
            "--accounts-file",
            str(file),
            "--operator-id",
            "OP-TEST",
            "--name",
            "Test operator",
            "--out",
            str(output),
        ],
    )
    with pytest.raises(SystemExit, match="--confirm-same-operator"):
        setup_main()
    assert not output.exists()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "operator-setup",
            "--accounts-file",
            str(file),
            "--operator-id",
            "OP-TEST",
            "--name",
            "Test operator",
            "--out",
            str(output),
            "--confirm-same-operator",
        ],
    )
    setup_main()
    assert output.is_file()
    op = checked_scrape_operator(
        load_operator_registry(output),
        ["first.creator", "second_creator"],
        operator_id="OP-TEST",
    )
    assert op.verified is True
    assert op.verification_method == "researcher_confirmed_same_operator_before_scrape"
    assert "not independent legal ownership" in capsys.readouterr().out.lower()
    with pytest.raises(SystemExit, match="Existing registry protected"):
        setup_main()


def test_grouping_fail_closed_before_provider_call(tmp_path: Path, monkeypatch, capsys) -> None:
    input_file = tmp_path / "accounts.txt"
    input_file.write_text("@alpha\n@beta\n", encoding="utf-8")
    path = _registered(tmp_path, ["alpha", "beta"])
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(scrape, "ApifyClient", lambda *a, **k: pytest.fail("API was called"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scrape",
            str(input_file),
            "--operators",
            str(path),
            "--preflight",
        ],
    )
    scrape_main()
    assert "Preflight PASS" in capsys.readouterr().out
    assert not (tmp_path / "tiktok_snapshot").exists()
    assert checked_scrape_operator(load_operator_registry(path), ["alpha"]).operator_id == "OP-TEST"
    with pytest.raises(ValueError, match="missing from confirmed"):
        checked_scrape_operator(load_operator_registry(path), ["alpha", "unseen"])
    with pytest.raises(ValueError, match="not user-confirmed"):
        checked_scrape_operator(
            load_operator_registry(_registered(tmp_path, ["alpha"], confirm=False)), ["alpha"]
        )


def test_scrape_blocks_unregistered_accounts_even_without_token(
    tmp_path: Path, monkeypatch
) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text("@legitimate\n@unregistered\n", encoding="utf-8")
    registry = _registered(tmp_path, ["legitimate"])
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scrape",
            str(targets),
            "--operators",
            str(registry),
        ],
    )
    with pytest.raises(SystemExit, match="Operator grouping preflight FAILED"):
        scrape_main()
    with pytest.raises(ValueError, match="does not own"):
        checked_scrape_operator(
            load_operator_registry(registry),
            ["legitimate"],
            operator_id="OP-OTHER",
        )


def test_project_setup_rejects_malformed_handles(tmp_path: Path) -> None:
    for invalid in ["https://example.com/a", "@name with spaces", "@a/b"]:
        p = tmp_path / "targets.txt"
        p.write_text(invalid + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid TikTok handle"):
            _accounts_file(p)
