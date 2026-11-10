import pytest

from app.core.agent_contract import AgentResult, BaseAgent
from app.scripts.evaluate_matching import EvaluationCase
from app.scripts.evaluate_matching_rag import evaluate_rag_cases, render_rag_report


class _MatchingAgent(BaseAgent):
    async def run(self, context):
        requirement = "Python"
        evidence = context.resume_text if "Python" in context.resume_text else ""
        status = "met" if evidence else "missing"
        output = {
            "score": 100 if evidence else 0,
            "verdict": "strong_match" if evidence else "weak_match",
            "reasoning": "Test result.",
            "matched_requirements": [requirement] if evidence else [],
            "missing_requirements": [] if evidence else [requirement],
            "suggestions": [],
            "jd_analysis": {
                "role_title": "Backend Engineer",
                "experience_level": None,
                "tech_stack": ["Python"],
                "requirements": [
                    {
                        "text": requirement,
                        "priority": "required",
                        "category": "skill",
                        "jd_quote": "Python is required.",
                    }
                ],
            },
            "requirement_assessments": [
                {"requirement_index": 0, "status": status, "cv_evidence": evidence}
            ],
        }
        return AgentResult(output=output, run_logs=[])


@pytest.mark.asyncio
async def test_rag_evaluation_uses_retrieved_context_and_reports_baseline_delta():
    case = EvaluationCase(
        case_id="python-case",
        resume_text="Built Python APIs. Deployed on AWS.",
        job_description="Python is required.",
        expected_verdict="strong_match",
        rationale="Python is explicitly documented.",
    )
    vectors = {
        "Built Python APIs.": [1.0, 0.0],
        "Deployed on AWS.": [0.0, 1.0],
        "Python": [0.9, 0.1],
    }

    async def fake_embed(text: str) -> list[float]:
        return vectors[text]

    outcomes = await evaluate_rag_cases(
        [case],
        _MatchingAgent(),
        minimum_similarity=0.25,
        embed=fake_embed,
    )
    report = render_rag_report(
        [case],
        outcomes,
        provider="test",
        model="fake",
        top_k_per_query=1,
        max_chunks=12,
        minimum_similarity=0.25,
        retrieval_strategy="hybrid",
    )

    assert outcomes[0]["baseline"]["actual"] == "strong_match"
    assert outcomes[0]["rag"]["actual"] == "strong_match"
    assert outcomes[0]["retrieved_chunks"] == 1
    assert "1/1 (100.0%)" in report
    assert "Retrieved-context RAG" in report
    assert "Retrieval strategy: `hybrid`" in report
