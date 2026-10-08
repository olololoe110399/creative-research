from __future__ import annotations

from pathlib import Path

import pytest

from creative_research.operator_registry import load_operator_registry


def test_load_operator_registry_maps_verified_accounts(tmp_path: Path) -> None:
    path = tmp_path / "operators.toml"
    path.write_text(
        """
schema_version = "operator-registry-v1"

[[operators]]
operator_id = "OP-001"
name = "Operator One"
verified = true
verification_method = "manual"

[[operators.accounts]]
username = "Creator_A"
platform = "tiktok"

[[operators.accounts]]
username = "@creator_b"
platform = "tiktok"
role = "unknown"
""".strip(),
        encoding="utf-8",
    )

    registry = load_operator_registry(path)
    mapping = registry.account_map()
    assert set(mapping) == {"creator_a", "creator_b"}
    assert mapping["creator_a"][0].operator_id == "OP-001"
    assert mapping["creator_a"][1].account_id.startswith("ACC-")


def test_registry_rejects_account_owned_by_two_operators(tmp_path: Path) -> None:
    path = tmp_path / "operators.toml"
    path.write_text(
        """
[[operators]]
operator_id = "OP-001"
name = "One"

[[operators.accounts]]
username = "same"

[[operators]]
operator_id = "OP-002"
name = "Two"

[[operators.accounts]]
username = "@same"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="belongs to both"):
        load_operator_registry(path)
