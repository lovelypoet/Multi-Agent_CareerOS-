import pytest

from app.scripts.evaluate_resume_retrieval import (
    RetrievalCase,
    evaluate_retrieval,
    render_retrieval_report,
)


@pytest.mark.asyncio
async def test_retrieval_evaluator_compares_dense_and_hybrid_with_labeled_evidence():
    case = RetrievalCase(
        case_id="python-api",
        resume_text="Built Python APIs. Designed scalable systems.",
        query="Python API development",
        expected_evidence=["Built Python APIs."],
    )
    vectors = {
        "Built Python APIs.": [0.7, 0.714142842],
        "Designed scalable systems.": [1.0, 0.0],
        "Python API development": [1.0, 0.0],
    }

    async def fake_embed(text: str) -> list[float]:
        return vectors[text]

    outcomes = await evaluate_retrieval([case], top_k=2, embed=fake_embed)
    report = render_retrieval_report(
        outcomes,
        model="fake",
        top_k=2,
        minimum_similarity=0.25,
    )

    assert outcomes[0]["dense"][0]["hit"] is False
    assert outcomes[0]["hybrid"][0]["hit"] is True
    assert "Recall@1 | 0.0% | 100.0%" in report


def test_retrieval_case_requires_expected_evidence():
    with pytest.raises(ValueError):
        RetrievalCase(
            case_id="missing-label",
            resume_text="Some resume.",
            query="some query",
            expected_evidence=[],
        )
