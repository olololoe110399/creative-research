from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from tests.skills.eval_cases import CASES


def report_for(rows):
    citations = [
        {
            "table": "data/06_analytics/eval.csv",
            "row": {"post_uid": row["post_uid"]},
            "metrics": {"views": row["views"], "saves": row["saves"]},
        }
        for row in rows
    ]
    return {
        "schema_version": "agent-research-v1",
        "kind": "strategy",
        "question": "Compare observed engagement",
        "scope": "OP1, synthetic fixture",
        "data_as_of": "unknown",
        "unknowns": ["No first-party outcomes or causal comparison"],
        "proposed_actions": ["Propose original variants and compare; obtain rights approval"],
        "findings": [
            {
                "id": "F1",
                "type": "observation" if rows else "unknown",
                "claim": "Fixture engagement is observed, not a causal or revenue claim"
                if rows
                else "Insufficient evidence",
                "confidence": "low",
                "confidence_reason": "Synthetic, limited scope",
                "source_evidence": citations,
                "counterevidence": [],
                "counterevidence_search": "Full supplied fixture inspected; no causal/outcome fields available",
            }
        ],
    }


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_workflow_eval_contracts_allow_explicitly_bounded_findings(skill_modules, tmp_path, case):
    _, validator, _ = skill_modules
    analytics = tmp_path / "data/06_analytics"
    analytics.mkdir(parents=True)
    if case["rows"]:
        pd.DataFrame(case["rows"]).to_csv(analytics / "eval.csv", index=False)
    assert validator.validate_report(report_for(case["rows"]), tmp_path) == []


@pytest.fixture
def sourced_report(tmp_path):
    rows = CASES[0]["rows"]
    analytics = tmp_path / "data/06_analytics"
    analytics.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(analytics / "eval.csv", index=False)
    return report_for(rows)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            lambda report: report["findings"][0]["source_evidence"][0]["metrics"].update(views=999),
            "differs from source",
        ),
        (
            lambda report: report["findings"][0]["source_evidence"][0]["row"].update(
                post_uid="invented"
            ),
            "exactly one",
        ),
        (lambda report: report["findings"][0].update(source_evidence=[]), "require verifiable"),
        (lambda report: report.update(unknowns=[]), "unknowns"),
        (
            lambda report: report["findings"][0].update(counterevidence_search=""),
            "explain explicitly",
        ),
        (
            lambda report: report["findings"][0].update(
                type="inference", alternative_explanations=[]
            ),
            "alternative_explanations",
        ),
        (lambda report: report.update(kind=[]), "kind research"),
        (lambda report: report["findings"][0].update(id=[], type=[], confidence=[]), "id must"),
    ],
)
def test_report_rejects_fabrication_and_malformed_input(
    skill_modules, tmp_path, sourced_report, mutation, expected
):
    _, validator, _ = skill_modules
    mutation(sourced_report)
    assert any(expected in error for error in validator.validate_report(sourced_report, tmp_path))


def test_singleton_inference_cannot_pass_as_high_confidence(
    skill_modules, tmp_path, sourced_report
):
    _, validator, _ = skill_modules
    finding = sourced_report["findings"][0]
    finding.update(type="inference", confidence="high", alternative_explanations=["selection bias"])
    finding["source_evidence"] = [finding["source_evidence"][0]] * 3
    assert any(
        "singleton" in error for error in validator.validate_report(sourced_report, tmp_path)
    )


def test_alternate_selectors_for_the_same_row_do_not_increase_evidence_count(
    skill_modules, tmp_path, sourced_report
):
    _, validator, _ = skill_modules
    finding = sourced_report["findings"][0]
    finding.update(type="inference", confidence="high", alternative_explanations=["selection bias"])
    first = finding["source_evidence"][0]
    alternate = copy.deepcopy(first)
    alternate["row"]["operator_id"] = "OP1"
    finding["source_evidence"] = [first, alternate]
    assert any(
        "singleton" in error for error in validator.validate_report(sourced_report, tmp_path)
    )


def test_distinct_source_rows_remain_distinct_with_duplicate_persisted_indexes(
    skill_modules, tmp_path, sourced_report
):
    _, validator, _ = skill_modules
    frame = pd.DataFrame(CASES[0]["rows"])
    frame.index = [7] * len(frame)
    frame.to_parquet(tmp_path / "data/06_analytics/eval.parquet", index=True)
    finding = sourced_report["findings"][0]
    finding.update(type="inference", confidence="high", alternative_explanations=["selection bias"])
    for citation in finding["source_evidence"]:
        citation["table"] = "data/06_analytics/eval.parquet"
    assert validator.validate_report(sourced_report, tmp_path) == []


def test_duplicate_and_ambiguous_citations_and_production_contract(
    skill_modules, tmp_path, sourced_report
):
    _, validator, _ = skill_modules
    sourced_report["findings"].append(copy.deepcopy(sourced_report["findings"][0]))
    assert any("unique" in error for error in validator.validate_report(sourced_report, tmp_path))
    sourced_report["findings"].pop()
    sourced_report["kind"] = "production"
    assert any(
        "rights_review" in error for error in validator.validate_report(sourced_report, tmp_path)
    )
    sourced_report.update(
        original_concept="New execution",
        rights_review="Original assets; pending human approval",
        measurement_plan="Compare proposed variants",
    )
    assert validator.validate_report(sourced_report, tmp_path) == []
    path = tmp_path / "data/06_analytics/eval.csv"
    path.write_text(path.read_text() + "P1,OP1,1000,40\n")
    assert any(
        "exactly one" in error for error in validator.validate_report(sourced_report, tmp_path)
    )


def test_validator_handles_csv_parquet_and_jsonl_preserving_ids_and_exact_metrics(
    skill_modules, tmp_path
):
    _, validator, _ = skill_modules
    frame = pd.DataFrame(
        [{"post_id": "001", "post_uid": "P1", "views": 1000, "ratio": 0.123456789}]
    )
    data = tmp_path / "data"
    data.mkdir()
    for extension in ("csv", "parquet", "jsonl"):
        path = data / f"source.{extension}"
        if extension == "parquet":
            frame.to_parquet(path, index=False)
        elif extension == "csv":
            frame.to_csv(path, index=False)
        else:
            path.write_text(json.dumps(frame.iloc[0].to_dict()) + "\n")
        report = report_for(CASES[0]["rows"][:1])
        citation = report["findings"][0]["source_evidence"][0]
        citation.update(
            table=f"data/source.{extension}", row={"post_id": "001"}, metrics={"ratio": 0.123456789}
        )
        assert validator.validate_report(report, tmp_path) == []


def test_validator_requires_separate_report_path_and_never_writes_sources(
    skill_modules, tmp_path, sourced_report, capsys
):
    _, validator, _ = skill_modules
    path = tmp_path / "data/report.json"
    path.write_text(json.dumps(sourced_report))
    assert validator.main(["--root", str(tmp_path), "data/report.json"]) == 1
    capsys.readouterr()
    reports = tmp_path / "agent-reports"
    reports.mkdir()
    report = reports / "test.json"
    report.write_text(json.dumps(sourced_report))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert validator.main(["--root", str(tmp_path), "agent-reports/test.json"]) == 0
    assert json.loads(capsys.readouterr().out)["reasoning_verified"] is False
    assert all(p.read_bytes() == content for p, content in before.items())
