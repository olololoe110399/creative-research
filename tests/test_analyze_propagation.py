from __future__ import annotations

import json

import pandas as pd

from creative_research.stages.analyze_propagation import build_propagation_tables


def _members() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "family_id": "F1",
                "operator_id": "OP1",
                "post_uid": "P1",
                "account_id": "A",
                "account": "a",
                "post_id": "1",
                "created_at": "2026-01-01T00:00:00Z",
                "content_type": "slideshow",
                "family_member_index": 1,
                "is_family_origin": True,
                "family_origin_post_uid": "P1",
                "match_score_to_origin": 1.0,
                "match_score_to_nearest_member": 1.0,
                "topic": "study mistakes",
                "content_angle": "study_method",
                "hook_text": "3 study mistakes",
                "hook_replicable_formula": "N study mistakes",
                "creative_formula": "hook -> problem -> value -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "problem", "value", "proof", "cta"]),
            },
            {
                "family_id": "F1",
                "operator_id": "OP1",
                "post_uid": "P2",
                "account_id": "B",
                "account": "b",
                "post_id": "2",
                "created_at": "2026-01-03T00:00:00Z",
                "content_type": "slideshow",
                "family_member_index": 2,
                "is_family_origin": False,
                "family_origin_post_uid": "P1",
                "match_score_to_origin": 0.90,
                "match_score_to_nearest_member": 0.90,
                "topic": "study mistakes",
                "content_angle": "study_method",
                "hook_text": "5 study mistakes",
                "hook_replicable_formula": "N study mistakes",
                "creative_formula": "hook -> problem -> value -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "problem", "value", "proof", "cta"]),
            },
            {
                "family_id": "F1",
                "operator_id": "OP1",
                "post_uid": "P3",
                "account_id": "B",
                "account": "b",
                "post_id": "3",
                "created_at": "2026-01-04T00:00:00Z",
                "content_type": "video",
                "family_member_index": 3,
                "is_family_origin": False,
                "family_origin_post_uid": "P1",
                "match_score_to_origin": 0.82,
                "match_score_to_nearest_member": 0.88,
                "topic": "study mistakes",
                "content_angle": "study_method",
                "hook_text": "stop making these study mistakes",
                "hook_replicable_formula": "N study mistakes",
                "creative_formula": "hook -> problem -> value -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "problem", "value", "proof", "cta"]),
            },
            {
                "family_id": "F1",
                "operator_id": "OP1",
                "post_uid": "P4",
                "account_id": "C",
                "account": "c",
                "post_id": "4",
                "created_at": "2026-01-05T00:00:00Z",
                "content_type": "video",
                "family_member_index": 4,
                "is_family_origin": False,
                "family_origin_post_uid": "P1",
                "match_score_to_origin": 0.78,
                "match_score_to_nearest_member": 0.86,
                "topic": "study mistakes",
                "content_angle": "study_method",
                "hook_text": "stop these mistakes before exams",
                "hook_replicable_formula": "N study mistakes",
                "creative_formula": "hook -> problem -> value -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "problem", "value", "proof", "cta"]),
            },
            {
                "family_id": "F2",
                "operator_id": "OP1",
                "post_uid": "P5",
                "account_id": "A",
                "account": "a",
                "post_id": "5",
                "created_at": "2026-01-10T00:00:00Z",
                "content_type": "slideshow",
                "family_member_index": 1,
                "is_family_origin": True,
                "family_origin_post_uid": "P5",
                "match_score_to_origin": 1.0,
                "match_score_to_nearest_member": 1.0,
                "topic": "active recall",
                "content_angle": "memorization",
                "hook_text": "stop rereading",
                "hook_replicable_formula": "stop X do Y",
                "creative_formula": "pain -> mechanism -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "problem", "value", "proof", "cta"]),
            },
            {
                "family_id": "F2",
                "operator_id": "OP1",
                "post_uid": "P6",
                "account_id": "B",
                "account": "b",
                "post_id": "6",
                "created_at": "2026-01-11T00:00:00Z",
                "content_type": "slideshow",
                "family_member_index": 2,
                "is_family_origin": False,
                "family_origin_post_uid": "P5",
                "match_score_to_origin": 0.91,
                "match_score_to_nearest_member": 0.91,
                "topic": "active recall",
                "content_angle": "memorization",
                "hook_text": "don't reread notes",
                "hook_replicable_formula": "stop X do Y",
                "creative_formula": "pain -> mechanism -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "problem", "value", "proof", "cta"]),
            },
            {
                "family_id": "F3",
                "operator_id": "OP1",
                "post_uid": "P7",
                "account_id": "B",
                "account": "b",
                "post_id": "7",
                "created_at": "2026-01-20T00:00:00Z",
                "content_type": "video",
                "family_member_index": 1,
                "is_family_origin": True,
                "family_origin_post_uid": "P7",
                "match_score_to_origin": 1.0,
                "match_score_to_nearest_member": 1.0,
                "topic": "exam prep",
                "content_angle": "exam_prep",
                "hook_text": "exam week plan",
                "hook_replicable_formula": "plan before exam",
                "creative_formula": "hook -> plan -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "value", "proof", "cta"]),
            },
            {
                "family_id": "F3",
                "operator_id": "OP1",
                "post_uid": "P8",
                "account_id": "C",
                "account": "c",
                "post_id": "8",
                "created_at": "2026-01-22T00:00:00Z",
                "content_type": "video",
                "family_member_index": 2,
                "is_family_origin": False,
                "family_origin_post_uid": "P7",
                "match_score_to_origin": 0.89,
                "match_score_to_nearest_member": 0.89,
                "topic": "exam prep",
                "content_angle": "exam_prep",
                "hook_text": "exam week checklist",
                "hook_replicable_formula": "plan before exam",
                "creative_formula": "hook -> plan -> proof -> cta",
                "sequence_roles_json": json.dumps(["hook", "value", "proof", "cta"]),
            },
        ]
    )


def _analysis() -> pd.DataFrame:
    rows = []
    values = {
        "P1": ("college_student", "none", "list_or_number", "listicle", None),
        "P2": ("college_student", "none", "list_or_number", "listicle", None),
        "P3": ("college_student", "none", "direct_address", None, "talking_head"),
        "P4": ("college_student", "none", "direct_address", None, "talking_head"),
        "P5": ("college_student", "none", "bold_claim", "problem_solution", None),
        "P6": ("college_student", "none", "bold_claim", "problem_solution", None),
        "P7": ("college_student", "none", "how_to", None, "tutorial"),
        "P8": ("college_student", "none", "how_to", None, "tutorial"),
    }
    for post_uid, (audience, product, hook, content_format, video_format) in values.items():
        rows.append(
            {
                "post_uid": post_uid,
                "audience_segment": audience,
                "product_family": product,
                "hook_technique": hook,
                "content_format": content_format,
                "video_format": video_format,
            }
        )
    return pd.DataFrame(rows)


def _performance() -> pd.DataFrame:
    values = {
        "P1": 0.70,
        "P2": 0.92,
        "P3": 0.85,
        "P4": 0.65,
        "P5": 0.80,
        "P6": 0.95,
        "P7": 0.60,
        "P8": 0.75,
    }
    return pd.DataFrame(
        [
            {
                "post_uid": post_uid,
                "views_percentile_account": percentile,
                "views_percentile_operator": percentile,
            }
            for post_uid, percentile in values.items()
        ]
    )


def test_propagation_tracks_family_entries_delays_and_variant_changes() -> None:
    tables = build_propagation_tables(_members(), _analysis(), _performance())

    entries = tables["family_account_entries"]
    f1_entries = entries.loc[entries["family_id"] == "F1"].sort_values("entry_order")
    assert list(f1_entries["account"]) == ["a", "b", "c"]
    assert list(f1_entries["entry_order"]) == [1, 2, 3]
    assert f1_entries.iloc[1]["days_since_family_origin"] == 2.0
    assert f1_entries.iloc[1]["posts_in_family_on_account"] == 2

    events = tables["cross_account_propagation"].set_index(
        ["family_id", "target_account_id"]
    )
    f1_b = events.loc[("F1", "B")]
    assert f1_b["origin_account_id"] == "A"
    assert f1_b["delay_from_family_origin_days"] == 2.0
    assert f1_b["target_first_post_uid"] == "P2"
    assert f1_b["target_outperformed_origin"] == True  # noqa: E712
    assert f1_b["target_vs_origin_views_percentile_delta"] == 0.22

    f1_c = events.loc[("F1", "C")]
    assert f1_c["preceding_account_id"] == "B"
    assert f1_c["preceding_family_post_uid"] == "P3"
    changed = json.loads(f1_c["changed_dimensions_json"])
    assert "content_type" in changed
    assert "format" in changed
    preserved = json.loads(f1_c["preserved_dimensions_json"])
    assert "topic" in preserved
    assert "content_angle" in preserved


def test_account_edges_distinguish_origin_edges_from_nearest_prior_sequence() -> None:
    tables = build_propagation_tables(_members(), _analysis(), _performance())

    origin_edges = tables["account_propagation_edges"].set_index(
        ["origin_account_id", "target_account_id"]
    )
    assert origin_edges.loc[("A", "B"), "families_observed"] == 2
    assert origin_edges.loc[("A", "C"), "families_observed"] == 1

    sequence_edges = tables["account_sequence_edges"].set_index(
        ["preceding_account_id", "target_account_id"]
    )
    assert sequence_edges.loc[("B", "C"), "families_observed"] == 2
    assert "sequence_not_causation" in sequence_edges.loc[("B", "C"), "interpretation"]


def test_account_role_evidence_is_descriptive_not_a_final_strategy_label() -> None:
    tables = build_propagation_tables(_members(), _analysis(), _performance())
    roles = tables["account_role_evidence"].set_index("account_id")

    assert roles.loc["A", "families_participated"] == 2
    assert roles.loc["A", "origin_families"] == 2
    assert roles.loc["A", "imported_families"] == 0
    assert roles.loc["A", "outbound_propagation_rate"] == 1.0
    assert roles.loc["A", "originator_signal"] == 1.0
    assert roles.loc["A", "descriptive_profile"] == "originator_leaning"

    assert roles.loc["C", "origin_families"] == 0
    assert roles.loc["C", "imported_families"] == 2
    assert roles.loc["C", "receiver_signal"] == 1.0
    assert roles.loc["C", "descriptive_profile"] == "receiver_leaning"

    assert "not a final" in roles.loc["A", "notes"]
