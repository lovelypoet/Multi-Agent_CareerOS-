"""Test `GET /api/jobs/search` (Phase 3 việc #4 mục 5) — tìm kiếm theo ý nghĩa, đường KHÁC với
lọc rẻ trong `fetch_jobs.py`: dùng `.cosine_distance()` của pgvector (SQL), không phải
`cosine_similarity()` Python thuần — job đã có embedding lưu THẬT trong DB test.
"""

from __future__ import annotations

import pytest

from app.core.db import SessionLocal
from app.integrations.embedding_client import EMBEDDING_DIM
from app.repositories.job_repository import JobRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _vec(*ones_at: int) -> list[float]:
    """Vector `EMBEDDING_DIM` chiều, đặt 1.0 ở các chỉ số trong `ones_at`, còn lại 0.0 — dễ
    kiểm soát khoảng cách cosine giữa các vector trong test hơn số thực ngẫu nhiên."""
    vector = [0.0] * EMBEDDING_DIM
    for index in ones_at:
        vector[index] = 1.0
    return vector


async def _create_job(*, title: str, embedding: list[float] | None) -> int:
    async with SessionLocal() as session:
        job = await JobRepository(session).create(
            description=f"Mo ta cho {title}", title=title, source="manual", embedding=embedding
        )
        await session.commit()
        return job.id


async def test_search_orders_by_closest_cosine_distance_first(client, fake_embedding_client):
    # job_close gần trùng query (similarity cao -> distance thấp), job_far gần trực giao.
    close_id = await _create_job(title="Data Engineer gan giong query", embedding=_vec(0, 1))
    far_id = await _create_job(title="Business Analyst khong lien quan", embedding=_vec(500))

    fake_embedding_client(vectors={"machine learning fresher": _vec(0, 1, 2)})

    response = await client.get("/api/jobs/search", params={"q": "machine learning fresher"})

    assert response.status_code == 200
    ids = [job["id"] for job in response.json()]
    assert ids.index(close_id) < ids.index(far_id)


async def test_job_without_embedding_does_not_appear_in_results(client, fake_embedding_client):
    with_embedding_id = await _create_job(title="Co embedding", embedding=_vec(0))
    without_embedding_id = await _create_job(title="Khong co embedding (job cu truoc tinh nang nay)", embedding=None)

    fake_embedding_client(vectors={"tim job bat ky": _vec(0)})

    response = await client.get("/api/jobs/search", params={"q": "tim job bat ky"})

    ids = [job["id"] for job in response.json()]
    assert with_embedding_id in ids
    assert without_embedding_id not in ids


async def test_search_limits_results_to_20(client, fake_embedding_client):
    for i in range(25):
        await _create_job(title=f"Job {i}", embedding=_vec(i))

    fake_embedding_client(vectors={"query bat ky": _vec(0)})

    response = await client.get("/api/jobs/search", params={"q": "query bat ky"})

    assert len(response.json()) == 20


async def test_search_embedding_call_error_returns_503(client, fake_embedding_client):
    from app.integrations.embedding_client import EmbeddingCallError

    fake_embedding_client(raise_error=EmbeddingCallError("gia lap ollama chua chay"))

    response = await client.get("/api/jobs/search", params={"q": "bat ky"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SEARCH_UNAVAILABLE"


async def test_empty_query_rejected_with_422(client):
    response = await client.get("/api/jobs/search", params={"q": ""})
    assert response.status_code == 422
