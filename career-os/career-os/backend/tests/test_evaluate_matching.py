from __future__ import annotations

import pytest

from app.core.agent_contract import AgentContext, AgentResult, AgentRunLog, BaseAgent
from app.scripts.evaluate_matching import (
    EvaluationCase,
    evaluate_cases,
    load_cases,
    render_report,
)
from app.integrations.itviec import JobListingMeta
from app.scripts.evaluate_live_jobs import build_synthetic_cases, select_diverse_listings

class FakeMatchingAgent(BaseAgent):
    name = "matching_agent"

    def __init__(self, responses: list[AgentResult]) -> None:
        self.responses = iter(responses)

    async def run(self, context: AgentContext) -> AgentResult:
        return next(self.responses)


def _case(case_id: str, verdict: str) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        resume_text="resume",
        job_description="job",
        expected_verdict=verdict,
        rationale="labeled rationale",
    )


def _result(verdict: str | None, *, needs_review: bool = False) -> AgentResult:
    output = None if verdict is None else {"verdict": verdict}
    log = AgentRunLog(
        agent_name="matching_agent",
        prompt_version="matching_v1",
        latency_ms=125,
        input_tokens=20,
        output_tokens=10,
        output=output,
        model="fake-model",
    )
    return AgentResult(output=output, run_logs=[log], needs_review=needs_review)


@pytest.mark.asyncio(loop_scope="session")
async def test_evaluate_cases_reports_correct_incorrect_and_review_outcomes():
    cases = [
        _case("correct", "strong_match"),
        _case("incorrect", "partial_match"),
        _case("review", "weak_match"),
    ]
    agent = FakeMatchingAgent(
        [
            _result("strong_match"),
            _result("good_match"),
            _result(None, needs_review=True),
        ]
    )

    outcomes = await evaluate_cases(cases, agent)
    report = render_report(cases, outcomes, provider="test")

    assert [outcome["status"] for outcome in outcomes] == [
        "correct",
        "incorrect",
        "needs_review",
    ]
    assert "Exact verdict accuracy: **1/3 (33.3%)**" in report
    assert "Macro F1 across the four verdicts" in report
    assert "`incorrect` | `partial_match` | predicted `good_match`" in report
    assert "`review` | `weak_match` | needs review (no verdict)" in report
    assert "fake-model" in report


def test_load_benchmark_dataset_has_balanced_labels():
    from app.scripts.evaluate_matching import DEFAULT_DATASET, VERDICTS

    cases = load_cases(DEFAULT_DATASET)
    assert len(cases) == 12
    assert {verdict: sum(case.expected_verdict == verdict for case in cases) for verdict in VERDICTS} == {
        "strong_match": 3,
        "good_match": 3,
        "partial_match": 3,
        "weak_match": 3,
    }


def test_live_job_benchmark_uses_distinct_companies_and_controlled_labels():
    listings = [
        JobListingMeta("AI Engineer A", "Same Co", "https://example.com/a", ["Python", "LLM", "RAG"]),
        JobListingMeta("AI Engineer duplicate", "Same Co", "https://example.com/b", ["Python", "LLM", "RAG"]),
        JobListingMeta("AI Engineer B", "Other Co", "https://example.com/c", ["Python", "PyTorch", "NLP"]),
    ]
    selected = select_diverse_listings(listings, limit=2)
    cases = build_synthetic_cases(
        selected,
        {
            "https://example.com/a": "Live posting A",
            "https://example.com/c": "Live posting C",
        },
    )

    assert [listing.url for listing in selected] == ["https://example.com/a", "https://example.com/c"]
    assert len(cases) == 8
    assert [case.expected_verdict for case in cases[:4]] == [
        "strong_match",
        "good_match",
        "partial_match",
        "weak_match",
    ]
    assert cases[0].job_description == "Live posting A"
    assert "No experience with RAG" in cases[1].resume_text
    assert cases[2].expected_verdict == "partial_match"
    assert cases[3].expected_verdict == "weak_match"


def test_live_job_benchmark_rejects_missing_description():
    listing = JobListingMeta("AI Engineer", "Example Co", "https://example.com/job", ["Python"])

    with pytest.raises(ValueError, match="Missing live job description"):
        build_synthetic_cases([listing], {})


def test_live_job_benchmark_rejects_insufficient_tags():
    listing = JobListingMeta("AI Engineer", "Example Co", "https://example.com/job", ["Python"])

    with pytest.raises(ValueError, match="at least two listing skill tags"):
        build_synthetic_cases([listing], {"https://example.com/job": "Live posting"})
