import pytest

from app.services.resume_retrieval import retrieve_resume_chunks, split_resume_chunks


def test_split_resume_chunks_preserves_sentence_and_bullet_sources():
    assert split_resume_chunks(
        "Built Python APIs.\n- Deployed services on AWS. Built Python APIs."
    ) == ["Built Python APIs.", "- Deployed services on AWS."]


@pytest.mark.asyncio
async def test_retrieval_selects_best_chunk_for_each_query_and_deduplicates():
    vectors = {
        "Built Python APIs.": [1.0, 0.0],
        "Deployed services on AWS.": [0.0, 1.0],
        "Python backend": [0.9, 0.1],
        "AWS cloud": [0.1, 0.9],
    }

    async def fake_embed(text: str) -> list[float]:
        return vectors[text]

    results = await retrieve_resume_chunks(
        "Built Python APIs. Deployed services on AWS.",
        ["Python backend", "AWS cloud"],
        minimum_similarity=0.5,
        embed=fake_embed,
    )

    assert [item.text for item in results] == [
        "Built Python APIs.",
        "Deployed services on AWS.",
    ]
    assert [item.query for item in results] == ["Python backend", "AWS cloud"]


@pytest.mark.asyncio
async def test_retrieval_returns_no_context_below_similarity_threshold():
    vectors = {"Resume evidence.": [1.0, 0.0], "Unrelated requirement": [0.0, 1.0]}

    async def fake_embed(text: str) -> list[float]:
        return vectors[text]

    results = await retrieve_resume_chunks(
        "Resume evidence.",
        ["Unrelated requirement"],
        minimum_similarity=0.25,
        embed=fake_embed,
    )

    assert results == []


@pytest.mark.asyncio
async def test_retrieval_rejects_invalid_limits():
    with pytest.raises(ValueError, match="top_k_per_query"):
        await retrieve_resume_chunks("Resume.", ["requirement"], top_k_per_query=0)


@pytest.mark.asyncio
async def test_hybrid_reranking_promotes_exact_skill_evidence_over_semantic_noise():
    vectors = {
        "Built Python APIs.": [0.7, 0.714142842],
        "Designed scalable systems.": [1.0, 0.0],
        "Python API development": [1.0, 0.0],
    }

    async def fake_embed(text: str) -> list[float]:
        return vectors[text]

    dense = await retrieve_resume_chunks(
        "Built Python APIs. Designed scalable systems.",
        ["Python API development"],
        strategy="dense",
        embed=fake_embed,
    )
    hybrid = await retrieve_resume_chunks(
        "Built Python APIs. Designed scalable systems.",
        ["Python API development"],
        top_k_per_query=2,
        strategy="hybrid",
        embed=fake_embed,
    )

    assert dense[0].text == "Designed scalable systems."
    assert hybrid[0].text == "Built Python APIs."
    assert hybrid[0].lexical_score > 0
    assert hybrid[0].rerank_score > hybrid[1].rerank_score
