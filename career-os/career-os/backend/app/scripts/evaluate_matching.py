"""Run a small, hand-labeled benchmark against the configured matching agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.agent_contract import AgentContext, AgentExecutionError, AgentResult, BaseAgent
from app.core.agent_registry import get_agent
from app.core.config import get_settings

Verdict = Literal["strong_match", "good_match", "partial_match", "weak_match"]
VERDICTS: tuple[Verdict, ...] = ("strong_match", "good_match", "partial_match", "weak_match")
DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "evals" / "matching.json"


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    resume_text: str
    job_description: str
    expected_verdict: Verdict
    rationale: str


def load_cases(path: Path) -> list[EvaluationCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Evaluation dataset must be a non-empty JSON array.")
    cases = [EvaluationCase.model_validate(item) for item in data]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Evaluation case_id values must be unique.")
    return cases


async def evaluate_cases(cases: list[EvaluationCase], agent: BaseAgent) -> list[dict]:
    outcomes: list[dict] = []
    for case in cases:
        try:
            result = await agent.run(
                AgentContext(
                    resume_text=case.resume_text,
                    job_description_text=case.job_description,
                )
            )
        except AgentExecutionError as exc:
            outcomes.append(
                {
                    "case_id": case.case_id,
                    "expected": case.expected_verdict,
                    "actual": None,
                    "status": "error",
                    "error": str(exc)[:240],
                    "run_logs": exc.run_logs,
                    "requirements_total": 0,
                    "requirements_with_cv_evidence": 0,
                    "score": None,
                }
            )
            continue

        output = result.output or {}
        analysis = output.get("jd_analysis") if isinstance(output, dict) else None
        requirements = analysis.get("requirements", []) if isinstance(analysis, dict) else []
        assessments = output.get("requirement_assessments", []) if isinstance(output, dict) else []
        evidenced = sum(
            1
            for assessment in assessments
            if isinstance(assessment, dict)
            and assessment.get("status") in {"met", "partial"}
            and assessment.get("cv_evidence")
        )

        if result.needs_review:
            status = "needs_review"
            actual = None
        elif result.output is None:
            status = "error"
            actual = None
        else:
            actual = result.output["verdict"]
            status = "correct" if actual == case.expected_verdict else "incorrect"

        outcomes.append(
            {
                "case_id": case.case_id,
                "expected": case.expected_verdict,
                "actual": actual,
                "status": status,
                "error": None,
                "run_logs": result.run_logs,
                "requirements_total": len(requirements),
                "requirements_with_cv_evidence": evidenced,
                "score": output.get("score") if isinstance(output, dict) else None,
            }
        )
    return outcomes


def _class_metrics(expected: list[str], predicted: list[str | None], label: str) -> tuple[float, float, float]:
    true_positives = sum(actual == label and guess == label for actual, guess in zip(expected, predicted))
    predicted_count = sum(guess == label for guess in predicted)
    support = sum(actual == label for actual in expected)
    precision = true_positives / predicted_count if predicted_count else 0.0
    recall = true_positives / support if support else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def render_report(
    cases: list[EvaluationCase],
    outcomes: list[dict],
    *,
    provider: str,
) -> str:
    if len(cases) != len(outcomes):
        raise ValueError("Each evaluation case must have exactly one outcome.")

    expected = [case.expected_verdict for case in cases]
    predicted = [outcome["actual"] for outcome in outcomes]
    correct = sum(outcome["status"] == "correct" for outcome in outcomes)
    metrics = {label: _class_metrics(expected, predicted, label) for label in VERDICTS}
    macro_f1 = sum(values[2] for values in metrics.values()) / len(VERDICTS)
    calls = [log for outcome in outcomes for log in outcome["run_logs"]]
    models = sorted({log.model for log in calls if log.model})
    prompts = sorted({log.prompt_version for log in calls if log.prompt_version})
    total_latency_ms = sum(log.latency_ms for log in calls)
    total_input_tokens = sum(log.input_tokens or 0 for log in calls)
    total_output_tokens = sum(log.output_tokens or 0 for log in calls)
    status_counts = Counter(outcome["status"] for outcome in outcomes)
    structured_cases = sum(outcome.get("requirements_total", 0) > 0 for outcome in outcomes)
    requirements_total = sum(outcome.get("requirements_total", 0) for outcome in outcomes)
    evidenced_requirements = sum(outcome.get("requirements_with_cv_evidence", 0) for outcome in outcomes)

    lines = [
        "# Matching agent evaluation",
        "",
        f"- Run date (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Provider: `{provider}`",
        f"- Model(s): {', '.join(f'`{model}`' for model in models) or 'not recorded'}",
        f"- Prompt version(s): {', '.join(f'`{prompt}`' for prompt in prompts) or 'not recorded'}",
        f"- Cases: {len(cases)}",
        "",
        "## Results",
        "",
        f"- Exact verdict accuracy: **{correct}/{len(cases)} ({correct / len(cases):.1%})**",
        f"- Macro F1 across the four verdicts: **{macro_f1:.3f}**",
        f"- Outcomes: {status_counts.get('correct', 0)} correct, "
        f"{status_counts.get('incorrect', 0)} incorrect, "
        f"{status_counts.get('needs_review', 0)} needs review, "
        f"{status_counts.get('error', 0)} errors",
        f"- Agent calls: {len(calls)}; summed model latency: {total_latency_ms / 1000:.1f}s; "
        f"tokens: {total_input_tokens:,} input / {total_output_tokens:,} output",
        f"- Structured JD analysis: {structured_cases}/{len(cases)} cases; "
        f"CV evidence quotes: {evidenced_requirements}/{requirements_total} assessed requirements",
        "",
        "| Verdict | Support | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in VERDICTS:
        precision, recall, f1 = metrics[label]
        support = sum(value == label for value in expected)
        lines.append(f"| `{label}` | {support} | {precision:.3f} | {recall:.3f} | {f1:.3f} |")

    failures = [
        (case, outcome)
        for case, outcome in zip(cases, outcomes)
        if outcome["status"] != "correct"
    ]
    lines.extend(["", "## Cases to review", ""])
    if not failures:
        lines.append("No incorrect, review-required, or failed cases in this run.")
    else:
        lines.extend(
            [
                "| Case | Expected | Result | Score | Structured requirements | Notes |",
                "|---|---|---|---:|---:|---|",
            ]
        )
        for case, outcome in failures:
            if outcome["status"] == "error":
                result = f"error: {outcome['error'] or 'no usable output'}"
            elif outcome["status"] == "needs_review":
                result = "needs review (no verdict)"
            else:
                result = f"predicted `{outcome['actual']}`"
            notes = case.rationale.replace("|", "\\|")
            score = outcome.get("score")
            requirements = outcome.get("requirements_total", 0)
            lines.append(
                f"| `{case.case_id}` | `{case.expected_verdict}` | {result} | "
                f"{score if score is not None else '—'} | {requirements} | {notes} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This 24-case balanced benchmark uses hand-authored synthetic resume/JD pairs. Labels "
            "are scenario-based annotations, not independently adjudicated hiring decisions or "
            "proof of production accuracy. Review case-level results and source-quote coverage; "
            "exact-verdict accuracy counts errors and review-required outcomes as incorrect.",
            "",
        ]
    )
    return "\n".join(lines)


async def _run(dataset: Path, output_path: Path | None) -> int:
    cases = load_cases(dataset)
    outcomes = await evaluate_cases(cases, get_agent("matching_agent"))
    report = render_report(cases, outcomes, provider=get_settings().llm_provider)
    if output_path is not None:
        output_path.write_text(report, encoding="utf-8")
    print(report)
    return 1 if any(outcome["status"] == "error" for outcome in outcomes) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, help="Also write the Markdown report to this path.")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.dataset, args.output)))


if __name__ == "__main__":
    main()
