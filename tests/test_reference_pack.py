from __future__ import annotations

from pathlib import Path

import pandas as pd

from creative_research.reference_pack import (
    REFERENCE_EXPORT_SCHEMA_VERSION,
    apply_conditions,
    build_reference_rows,
    copy_reference_media,
    group_references,
    rank_master,
    select_reference_candidates,
)


def sample() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "account": "a",
                "post_id": "1",
                "url": "https://example.com/1",
                "content_type": "slideshow",
                "views": 100,
                "account_views_pct": 0.50,
                "global_views_pct": 0.40,
                "save_rate": 0.01,
                "share_rate": 0.01,
                "hook_technique": "question",
                "content_angle": "education",
                "content_format": "list",
                "product_placement_style": "late",
                "source_media_path": "data/media/a/1",
            },
            {
                "account": "a",
                "post_id": "2",
                "url": "https://example.com/2",
                "content_type": "slideshow",
                "views": 1000,
                "account_views_pct": 0.95,
                "global_views_pct": 0.90,
                "save_rate": 0.05,
                "share_rate": 0.02,
                "hook_technique": "list",
                "content_angle": "education",
                "content_format": "list",
                "product_placement_style": "late",
                "source_media_path": "data/media/a/2",
            },
            {
                "account": "b",
                "post_id": "3",
                "url": "https://example.com/3",
                "content_type": "slideshow",
                "views": 800,
                "account_views_pct": 0.85,
                "global_views_pct": 0.80,
                "save_rate": 0.03,
                "share_rate": 0.04,
                "hook_technique": "list",
                "content_angle": "education",
                "content_format": "list",
                "product_placement_style": "late",
                "source_media_path": "data/media/b/3",
            },
            {
                "account": "b",
                "post_id": "4",
                "url": "https://example.com/4",
                "content_type": "video",
                "views": 5000,
                "account_views_pct": 0.99,
                "global_views_pct": 0.99,
                "save_rate": 0.02,
                "share_rate": 0.01,
                "hook_technique": "direct",
                "content_angle": "demo",
                "content_format": pd.NA,
                "product_placement_style": "early",
                "source_media_path": "data/video/b/4",
            },
        ]
    )


def test_rank_posts_prefers_account_relative_performance() -> None:
    ranked = rank_master(sample(), rank="relative", content_type="slideshow", top=2)
    assert ranked["post_id"].tolist() == ["2", "3"]
    assert ranked["rank_score"].tolist() == [0.95, 0.85]


def test_build_reference_rows_has_stable_contract() -> None:
    ranked = rank_master(sample(), rank="relative", content_type="slideshow", top=2)
    refs = build_reference_rows(ranked, rank_mode="relative")
    assert refs["reference_id"].tolist() == ["REF-0001", "REF-0002"]
    assert set(refs["reference_schema_version"]) == {REFERENCE_EXPORT_SCHEMA_VERSION}
    assert refs["source_account"].tolist() == ["a", "b"]
    assert refs["source_post_id"].tolist() == ["2", "3"]


def test_conditions_are_explicit_and_safe() -> None:
    result = apply_conditions(
        sample(),
        ["content_type=slideshow", "account_views_pct>=0.85", "views<900"],
    )
    assert result["post_id"].tolist() == ["3"]


def test_group_references_is_descriptive_not_family_assignment() -> None:
    refs = build_reference_rows(
        rank_master(sample(), rank="relative", content_type="slideshow"),
        rank_mode="relative",
    )
    groups = group_references(
        refs,
        dimensions=["hook_technique", "content_angle", "product_placement_style"],
    )
    list_group = groups.loc[groups["hook_technique"] == "list"].iloc[0]
    assert list_group["posts"] == 2
    assert list_group["accounts"] == 2
    assert list_group["top25_rate"] == 1.0


def test_copy_reference_media_uses_reference_ids(tmp_path: Path) -> None:
    source = tmp_path / "data/media/a/2"
    source.mkdir(parents=True)
    (source / "slide_001.jpg").write_bytes(b"fake")
    ranked = rank_master(sample().iloc[[1]], rank="relative")
    refs = build_reference_rows(ranked, rank_mode="relative")
    copied = copy_reference_media(refs, tmp_path / "pack", root=tmp_path)
    assert copied.loc[0, "media_path"] == "media/REF-0001"
    assert (tmp_path / "pack/media/REF-0001/slide_001.jpg").read_bytes() == b"fake"


def test_system_strategy_covers_accounts_before_more_from_strong_account() -> None:
    df = pd.DataFrame(
        [
            {"account": "a", "post_id": "a1", "content_type": "slideshow", "views": 10000, "account_views_pct": 0.99, "global_views_pct": 0.99, "save_rate": 0.05, "share_rate": 0.01, "hook_technique": "list", "content_angle": "education", "content_format": "list", "product_placement_style": "late"},
            {"account": "a", "post_id": "a2", "content_type": "slideshow", "views": 9000, "account_views_pct": 0.98, "global_views_pct": 0.98, "save_rate": 0.04, "share_rate": 0.01, "hook_technique": "list", "content_angle": "education", "content_format": "list", "product_placement_style": "late"},
            {"account": "a", "post_id": "a3", "content_type": "slideshow", "views": 8000, "account_views_pct": 0.97, "global_views_pct": 0.97, "save_rate": 0.03, "share_rate": 0.01, "hook_technique": "question", "content_angle": "education", "content_format": "list", "product_placement_style": "late"},
            {"account": "b", "post_id": "b1", "content_type": "slideshow", "views": 700, "account_views_pct": 0.70, "global_views_pct": 0.40, "save_rate": 0.02, "share_rate": 0.01, "hook_technique": "direct_address", "content_angle": "pain", "content_format": "story", "product_placement_style": "soft"},
            {"account": "c", "post_id": "c1", "content_type": "slideshow", "views": 600, "account_views_pct": 0.60, "global_views_pct": 0.30, "save_rate": 0.02, "share_rate": 0.01, "hook_technique": "how_to", "content_angle": "tutorial", "content_format": "tutorial", "product_placement_style": "none"},
        ]
    )
    _, selected = select_reference_candidates(
        df,
        strategy="system",
        rank="relative",
        content_type="slideshow",
        top=3,
    )
    assert set(selected["account"]) == {"a", "b", "c"}
    assert set(selected["selection_reason"]) == {"account_coverage"}


def test_account_balanced_strategy_limits_account_dominance() -> None:
    df = pd.DataFrame(
        [
            {"account": account, "post_id": f"{account}{i}", "content_type": "slideshow", "views": 1000 - i, "account_views_pct": 1 - i / 10, "global_views_pct": 0.5, "save_rate": 0.02, "share_rate": 0.01}
            for account in ("a", "b", "c")
            for i in range(3)
        ]
    )
    _, selected = select_reference_candidates(
        df,
        strategy="account-balanced",
        rank="relative",
        content_type="slideshow",
        top=7,
    )
    counts = selected["account"].value_counts()
    assert counts.max() - counts.min() <= 1


def test_system_strategy_soft_caps_account_concentration() -> None:
    rows = []
    for account, base in (("a", 0.99), ("b", 0.75), ("c", 0.65)):
        for i in range(10):
            rows.append(
                {
                    "account": account,
                    "post_id": f"{account}{i}",
                    "content_type": "slideshow",
                    "views": 10000 - i,
                    "account_views_pct": max(0.01, base - i * 0.01),
                    "global_views_pct": max(0.01, base - i * 0.01),
                    "save_rate": 0.03,
                    "share_rate": 0.01,
                    "hook_technique": "list" if i % 2 == 0 else "question",
                    "content_angle": "education",
                    "content_format": "listicle",
                    "product_placement_style": "late_reveal",
                    "audience_segment": "student",
                    "primary_language_code": "en",
                    "dominant_visual_type": "notes",
                }
            )
    _, selected = select_reference_candidates(
        pd.DataFrame(rows),
        strategy="system",
        rank="relative",
        content_type="slideshow",
        top=9,
    )
    counts = selected["account"].value_counts()
    assert set(counts.index) == {"a", "b", "c"}
    assert counts.max() <= 4
