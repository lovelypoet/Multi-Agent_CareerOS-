"""Test script `scripts/retry_missing_analyses.py` — dùng FakeAnthropicClient giống Phase 0
(`conftest.py`), không gọi mạng thật.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import AgentRun, Job, MatchResult
from app.scripts.retry_missing_analyses import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _save_resume(client, content: str = "3 nam React, TypeScript co ban."):
    return await client.post("/api/resume", json={"content": content})


async def _create_job(description: str = "JD bat ky") -> int:
    async with SessionLocal() as session:
        job = Job(description=description)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


async def test_no_resume_stops_immediately(client, fake_agent):
    fake_client = fake_agent(responses=["unused"])
    await _create_job()

    await run()

    assert len(fake_client.calls) == 0
    assert await _count(MatchResult) == 0
    assert await _count(AgentRun) == 0


async def test_job_already_has_match_result_is_not_reprocessed(client, fake_agent, valid_match_json):
    await _save_resume(client)
    job_id = await _create_job()
    async with SessionLocal() as session:
        session.add(
            MatchResult(
                job_id=job_id,
                resume_id=1,
                score=80,
                verdict="strong_match",
                reasoning="da co san tu truoc",
                matched_requirements=[],
                missing_requirements=[],
                suggestions=[],
            )
        )
        await session.commit()

    fake_client = fake_agent(responses=[valid_match_json])
    await run()

    assert len(fake_client.calls) == 0  # không gọi agent cho job đã có match_result
    assert await _count(MatchResult) == 1  # không tạo thêm row thứ 2


async def test_job_without_match_result_is_processed_and_saved(client, fake_agent, valid_match_json):
    await _save_resume(client)
    job_id = await _create_job("Can Data Engineer, uu tien Python")

    fake_client = fake_agent(responses=[valid_match_json])
    await run()

    assert len(fake_client.calls) == 1
    assert await _count(MatchResult) == 1
    async with SessionLocal() as session:
        match = (await session.execute(select(MatchResult))).scalar_one()
    assert match.job_id == job_id
    assert match.score == 72  # đúng theo valid_match_json fixture của conftest.py

    async with SessionLocal() as session:
        agent_run = (await session.execute(select(AgentRun))).scalar_one()
    assert agent_run.error is None
    assert agent_run.job_id == job_id


async def test_one_failed_job_does_not_stop_the_batch(client, fake_agent, valid_match_json):
    await _save_resume(client)
    job_a = await _create_job("Job A - se loi")
    job_b = await _create_job("Job B - se thanh cong")

    # list_without_match_result() order by created_at ASC -> job_a xử lý trước, job_b sau.
    fake_client = fake_agent(responses=["khong phai json hop le", valid_match_json])
    await run()

    assert len(fake_client.calls) == 2  # cả 2 job đều được thử, không dừng giữa chừng

    assert await _count(MatchResult) == 1
    async with SessionLocal() as session:
        match = (await session.execute(select(MatchResult))).scalar_one()
    assert match.job_id == job_b

    async with SessionLocal() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
    assert len(runs) == 2
    failed_run = next(r for r in runs if r.job_id == job_a)
    ok_run = next(r for r in runs if r.job_id == job_b)
    assert failed_run.error is not None
    assert ok_run.error is None


async def test_no_missing_jobs_is_a_noop(client, fake_agent):
    await _save_resume(client)
    fake_client = fake_agent(responses=["unused"])

    await run()  # không có job nào cả

    assert len(fake_client.calls) == 0
    assert await _count(MatchResult) == 0
