"""
Scoring Agent evaluation harness.

Runs the Scoring Agent against data/eval/ai_native_b2b_eval_set.yaml (25
hand-labeled synthetic companies — see that file's docstring for why
synthetic), grades each result against the human-assigned expected_band,
and reports:
- overall agreement rate (does the score fall in the same band a human assigned?)
- per-band precision/recall/F1 (treating reject/review/ready as 3 classes)
- a confusion matrix
- mean latency and total cost per run — architecture.md's evaluation plan
  explicitly calls for tracking both, not just accuracy alone

Run for real (requires a valid GEMINI_API_KEY):
    python -m src.eval.run_eval

This makes 25 real Scoring Agent calls against the live Gemini API — free
tier, but still not something to run in CI on every commit (rate limits).
The
harness's grading/aggregation logic is unit-tested with a fake score_fn
(see tests/eval/test_run_eval.py) so it's verified without spending API
credits or needing network access.
"""
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.agents.scoring_agent import score_lead
from src.core.icp import ICPConfig, get_icp_config
from src.schemas.lead import ResearchOutput, Signal

DEFAULT_EVAL_SET_PATH = (
    Path(__file__).parents[2] / "data" / "eval" / "ai_native_b2b_eval_set.yaml"
)
DEFAULT_RESULTS_DIR = Path(__file__).parents[2] / "eval_results"

BANDS = ("reject", "review", "ready")


@dataclass
class EvalCase:
    company_name: str
    domain: str | None
    expected_band: str
    research: ResearchOutput


def load_eval_set(path: Path | str = DEFAULT_EVAL_SET_PATH) -> list[EvalCase]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"eval set not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cases = []
    for entry in raw["companies"]:
        research = ResearchOutput(
            summary=entry["research"]["summary"].strip(),
            signals=[Signal(**s) for s in entry["research"]["signals"]],
            sources=entry["research"]["sources"],
        )
        cases.append(
            EvalCase(
                company_name=entry["company_name"],
                domain=entry.get("domain"),
                expected_band=entry["expected_band"],
                research=research,
            )
        )

    if not cases:
        raise ValueError(f"eval set at {path} contains no companies")
    return cases


@dataclass
class EvalCaseResult:
    company_name: str
    expected_band: str
    predicted_band: str | None
    score: int | None
    confidence: float | None
    reasoning: str | None
    latency_ms: int
    cost_usd: float | None
    agree: bool
    success: bool
    error: str | None = None


@dataclass
class EvalReport:
    total_cases: int
    agreement_count: int
    agreement_rate: float
    confusion_matrix: dict[str, dict[str, int]]
    precision_recall_f1: dict[str, dict[str, float]]
    mean_latency_ms: float
    total_cost_usd: float | None
    generated_at: str
    cases: list[EvalCaseResult] = field(default_factory=list)


def run_eval(
    eval_set: list[EvalCase] | None = None,
    icp: ICPConfig | None = None,
    score_fn: Callable = score_lead,
) -> EvalReport:
    """
    score_fn defaults to the real score_lead (makes real Gemini API
    calls when actually run). Tests inject a fake with the same signature
    to verify grading/aggregation logic without hitting the network — the
    harness's correctness (confusion matrix math, precision/recall,
    agreement rate) is independent of whether the LLM call is real.
    """
    icp = icp or get_icp_config()
    eval_set = eval_set if eval_set is not None else load_eval_set()

    case_results: list[EvalCaseResult] = []
    confusion: dict[str, dict[str, int]] = {b: {b2: 0 for b2 in BANDS} for b in BANDS}

    for case in eval_set:
        result = score_fn(case.research, icp)

        if not result.success:
            case_results.append(
                EvalCaseResult(
                    company_name=case.company_name,
                    expected_band=case.expected_band,
                    predicted_band=None,
                    score=None,
                    confidence=None,
                    reasoning=None,
                    latency_ms=result.latency_ms,
                    cost_usd=result.cost_usd,
                    agree=False,
                    success=False,
                    error=result.error,
                )
            )
            continue

        predicted_band = icp.band_for_score(result.output.score)
        agree = predicted_band == case.expected_band
        confusion[case.expected_band][predicted_band] += 1

        case_results.append(
            EvalCaseResult(
                company_name=case.company_name,
                expected_band=case.expected_band,
                predicted_band=predicted_band,
                score=result.output.score,
                confidence=result.output.confidence,
                reasoning=result.output.reasoning,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
                agree=agree,
                success=True,
            )
        )

    successful = [c for c in case_results if c.success]
    agreement_count = sum(1 for c in successful if c.agree)
    agreement_rate = agreement_count / len(successful) if successful else 0.0

    precision_recall_f1: dict[str, dict[str, float]] = {}
    for band in BANDS:
        tp = confusion[band][band]
        fp = sum(confusion[other][band] for other in BANDS if other != band)
        fn = sum(confusion[band][other] for other in BANDS if other != band)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        precision_recall_f1[band] = {"precision": precision, "recall": recall, "f1": f1}

    mean_latency_ms = (
        sum(c.latency_ms for c in case_results) / len(case_results) if case_results else 0.0
    )
    costs = [c.cost_usd for c in case_results]
    total_cost_usd = None if any(c is None for c in costs) else sum(costs)

    return EvalReport(
        total_cases=len(case_results),
        agreement_count=agreement_count,
        agreement_rate=agreement_rate,
        confusion_matrix=confusion,
        precision_recall_f1=precision_recall_f1,
        mean_latency_ms=mean_latency_ms,
        total_cost_usd=total_cost_usd,
        generated_at=datetime.now(timezone.utc).isoformat(),
        cases=case_results,
    )


def print_report(report: EvalReport) -> None:
    print(f"\n=== Scoring Agent Evaluation — {report.generated_at} ===")
    print(
        f"Cases: {report.total_cases}  "
        f"Agreement: {report.agreement_count}/{report.total_cases} "
        f"({report.agreement_rate:.1%})"
    )
    cost_str = "unknown" if report.total_cost_usd is None else f"${report.total_cost_usd:.4f}"
    print(f"Mean latency: {report.mean_latency_ms:.0f}ms  Total cost: {cost_str}")

    print("\nPer-band precision / recall / F1:")
    for band, metrics in report.precision_recall_f1.items():
        print(
            f"  {band:>7}: P={metrics['precision']:.2f}  "
            f"R={metrics['recall']:.2f}  F1={metrics['f1']:.2f}"
        )

    print("\nConfusion matrix (rows=expected, cols=predicted):")
    print("          " + "".join(f"{b:>10}" for b in BANDS))
    for expected in BANDS:
        row = "".join(f"{report.confusion_matrix[expected][b]:>10}" for b in BANDS)
        print(f"{expected:>10}{row}")

    disagreements = [c for c in report.cases if c.success and not c.agree]
    if disagreements:
        print("\nDisagreements (worth reviewing):")
        for c in disagreements:
            print(
                f"  - {c.company_name}: expected={c.expected_band}, got={c.predicted_band} "
                f"(score={c.score}, confidence={c.confidence})"
            )

    failures = [c for c in report.cases if not c.success]
    if failures:
        print("\nAgent failures (excluded from agreement rate):")
        for c in failures:
            print(f"  - {c.company_name}: {c.error}")


def save_report(report: EvalReport, results_dir: Path = DEFAULT_RESULTS_DIR) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = results_dir / f"eval_report_{timestamp}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)
    return out_path


def main() -> None:
    report = run_eval()
    print_report(report)
    out_path = save_report(report)
    print(f"\nFull report saved to {out_path}")


if __name__ == "__main__":
    main()
