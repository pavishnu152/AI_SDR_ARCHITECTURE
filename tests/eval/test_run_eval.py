"""
Tests for the eval harness's grading/aggregation logic. A fake score_fn is
injected — these tests verify the harness's math (confusion matrix,
precision/recall, agreement rate, cost aggregation), not the Scoring
Agent's actual judgment (that's test_scoring_agent.py's job). No real API
calls, no network.
"""
from pathlib import Path

import pytest

from src.agents.scoring_agent import ScoringAgentResult
from src.core.icp import ICPConfig
from src.eval.run_eval import (
    DEFAULT_EVAL_SET_PATH,
    EvalCase,
    load_eval_set,
    run_eval,
    save_report,
)
from src.schemas.lead import ResearchOutput, ScoreOutput, Signal

REAL_ICP_PATH = Path(__file__).parents[2] / "configs" / "icp_ai_native_b2b.yaml"


def _case(name: str, expected_band: str) -> EvalCase:
    return EvalCase(
        company_name=name,
        domain=None,
        expected_band=expected_band,
        research=ResearchOutput(
            summary=f"Summary for {name}.",
            signals=[Signal(label="recent_funding", detail="...", source_url="https://x")],
            sources=["https://x"],
        ),
    )


def _fake_score_result(score: int) -> ScoringAgentResult:
    return ScoringAgentResult(
        success=True,
        output=ScoreOutput(score=score, confidence=0.8, reasoning="fake"),
        model="claude-haiku-4-5-20251001",
        latency_ms=100,
        input_tokens=200,
        output_tokens=50,
        cost_usd=0.0005,
    )


def test_load_eval_set_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        load_eval_set("data/eval/does_not_exist.yaml")


def test_load_eval_set_raises_on_empty_dataset(tmp_path):
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("companies: []\n")

    with pytest.raises(ValueError, match="no companies"):
        load_eval_set(empty_file)


def test_load_eval_set_loads_all_companies_with_valid_bands():
    cases = load_eval_set(DEFAULT_EVAL_SET_PATH)

    assert len(cases) == 25
    assert all(c.expected_band in ("reject", "review", "ready") for c in cases)
    band_counts = {b: sum(1 for c in cases if c.expected_band == b) for b in ("reject", "review", "ready")}
    assert band_counts == {"reject": 8, "review": 8, "ready": 9}


def test_run_eval_perfect_agreement():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)
    eval_set = [
        _case("A", "ready"),
        _case("B", "review"),
        _case("C", "reject"),
    ]
    scores_by_company = {"A": 85, "B": 55, "C": 20}

    def fake_score_fn(research, icp_arg):
        # Match the case by summary text since that's all the fake carries.
        for name, score in scores_by_company.items():
            if f"for {name}." in research.summary:
                return _fake_score_result(score)
        raise AssertionError("unmatched case")

    report = run_eval(eval_set=eval_set, icp=icp, score_fn=fake_score_fn)

    assert report.agreement_rate == 1.0
    assert report.agreement_count == 3
    for band_metrics in report.precision_recall_f1.values():
        if band_metrics["precision"] or band_metrics["recall"]:
            assert band_metrics["f1"] == 1.0


def test_run_eval_confusion_matrix_and_precision_recall():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)
    eval_set = [
        _case("Ready1", "ready"),
        _case("Ready2Misclassified", "ready"),  # will be scored into "review"
        _case("Review1", "review"),
        _case("Reject1", "reject"),
    ]

    def fake_score_fn(research, icp_arg):
        if "Ready1" in research.summary:
            return _fake_score_result(85)
        if "Ready2Misclassified" in research.summary:
            return _fake_score_result(55)  # lands in "review" band, wrong
        if "Review1" in research.summary:
            return _fake_score_result(55)
        if "Reject1" in research.summary:
            return _fake_score_result(10)
        raise AssertionError("unmatched case")

    report = run_eval(eval_set=eval_set, icp=icp, score_fn=fake_score_fn)

    assert report.agreement_count == 3
    assert report.agreement_rate == pytest.approx(0.75)

    assert report.confusion_matrix["ready"]["ready"] == 1
    assert report.confusion_matrix["ready"]["review"] == 1
    assert report.confusion_matrix["review"]["review"] == 1
    assert report.confusion_matrix["reject"]["reject"] == 1

    ready_metrics = report.precision_recall_f1["ready"]
    assert ready_metrics["precision"] == pytest.approx(1.0)
    assert ready_metrics["recall"] == pytest.approx(0.5)

    review_metrics = report.precision_recall_f1["review"]
    assert review_metrics["precision"] == pytest.approx(0.5)
    assert review_metrics["recall"] == pytest.approx(1.0)

    reject_metrics = report.precision_recall_f1["reject"]
    assert reject_metrics["precision"] == pytest.approx(1.0)
    assert reject_metrics["recall"] == pytest.approx(1.0)


def test_run_eval_excludes_agent_failures_from_agreement_rate():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)
    eval_set = [_case("Good", "ready"), _case("Broken", "ready")]

    def fake_score_fn(research, icp_arg):
        if "Broken" in research.summary:
            return ScoringAgentResult(
                success=False, output=None, model="claude-haiku-4-5-20251001",
                latency_ms=50, error="LLM call failed: timeout",
            )
        return _fake_score_result(85)

    report = run_eval(eval_set=eval_set, icp=icp, score_fn=fake_score_fn)

    assert report.total_cases == 2
    assert report.agreement_count == 1  # only "Good" counted
    assert report.agreement_rate == 1.0  # 1/1 successful cases agreed
    failed_case = next(c for c in report.cases if c.company_name == "Broken")
    assert failed_case.success is False
    assert failed_case.error == "LLM call failed: timeout"


def test_run_eval_total_cost_is_none_if_any_case_cost_unknown():
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)
    eval_set = [_case("A", "ready"), _case("B", "ready")]

    def fake_score_fn(research, icp_arg):
        result = _fake_score_result(85)
        if "B" in research.summary:
            result.cost_usd = None
        return result

    report = run_eval(eval_set=eval_set, icp=icp, score_fn=fake_score_fn)

    assert report.total_cost_usd is None


def test_save_report_writes_valid_json(tmp_path):
    icp = ICPConfig.from_yaml(REAL_ICP_PATH)
    eval_set = [_case("A", "ready")]

    report = run_eval(eval_set=eval_set, icp=icp, score_fn=lambda r, i: _fake_score_result(85))

    out_path = save_report(report, results_dir=tmp_path)

    assert out_path.exists()
    import json

    with out_path.open() as f:
        data = json.load(f)
    assert data["total_cases"] == 1
    assert data["agreement_rate"] == 1.0
