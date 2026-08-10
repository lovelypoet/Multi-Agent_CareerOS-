"""Test script `scripts/retry_missing_analyses.py` — dùng FakeAnthropicClient giống Phase 0
(`conftest.py`), không gọi mạng thật.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.agents.matching_agent import MatchingAgent
from app.core.agent_contract import AgentContext, AgentExecutionError
from app.core.db import SessionLocal
from app.models import AgentRun, Job, MatchResult
from app.repositories.agent_run_repository import AgentRunRepository
from app.scripts.retry_missing_analyses import run
from tests.conftest import FakeAnthropicClient

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

    # Lọc theo agent_name='matching_agent' — _save_resume() giờ CŨNG ghi 1 agent_runs cho
    # cv_extraction_agent (chạy tự động sau khi lưu resume, xem Phase 3 việc #4), không lọc sẽ
    # vỡ scalar_one() (>1 row).
    async with SessionLocal() as session:
        agent_run = (
            await session.execute(select(AgentRun).where(AgentRun.agent_name == "matching_agent"))
        ).scalar_one()
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

    # Lọc theo agent_name='matching_agent' — cùng lý do như test ở trên.
    async with SessionLocal() as session:
        runs = (
            await session.execute(select(AgentRun).where(AgentRun.agent_name == "matching_agent"))
        ).scalars().all()
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


async def _create_needs_review_job(description: str = "JD bat dong that su") -> int:
    """Tạo job THẬT rơi vào `needs_review` qua đúng cơ chế ensemble (2 client giả bất đồng
    verdict) — KHÔNG insert thẳng dữ liệu giả lập trạng thái. `needs_review` là kết quả THẬT của
    reconciliation logic trong `MatchingAgent.run()` (giống cách `test_matching_agent_ensemble.py`
    verify bất đồng), để test này không bị nghi ngờ là "giả lập cho khớp kỳ vọng"."""
    job_id = await _create_job(description)

    client_a = FakeAnthropicClient(
        responses=[
            '{"score": 65, "verdict": "good_match", "reasoning": "qwen than trong", '
            '"matched_requirements": [], "missing_requirements": [], "suggestions": []}'
        ]
    )
    client_a.model = "qwen2.5:7b"
    client_b = FakeAnthropicClient(
        responses=[
            '{"score": 85, "verdict": "strong_match", "reasoning": "llama lac quan", '
            '"matched_requirements": [], "missing_requirements": [], "suggestions": []}'
        ]
    )
    client_b.model = "llama3.1:8b"
    ensemble_agent = MatchingAgent(ensemble_clients=[client_a, client_b])

    async with SessionLocal() as session:
        result = await ensemble_agent.run(
            AgentContext(resume_text="CV", job_description_text=description, job_id=job_id)
        )
        assert result.needs_review is True  # sanity check: đúng là needs_review thật, không phải lỗi setup

        run_repo = AgentRunRepository(session)
        for log in result.run_logs:
            await run_repo.log(run_log=log, job_id=job_id)
        await session.commit()

    return job_id


async def test_needs_review_job_is_never_retried_but_failed_and_pending_are(
    client, fake_agent, valid_match_json
):
    """BUG ĐÃ VERIFY VÀ SỬA (`JobRepository.list_without_match_result`): bản cũ chỉ check "không
    có match_result", gộp chung `needs_review` (2 model bất đồng có chủ đích) với `failed`/
    `pending` (lỗi kỹ thuật thật) — retry nhầm cả job đang cố tình chờ người xem lại thủ công.

    Test này tạo đủ 3 trạng thái THẬT (không mock trạng thái, chỉ mock response LLM để mỗi
    trạng thái tự được tính ra đúng bằng code thật): `pending` (chưa từng chạy agent), `failed`
    (chạy thật nhưng response không phải JSON hợp lệ), `needs_review` (ensemble thật, 2 model
    bất đồng verdict thật) — chạy script, xác nhận CHỈ `failed`/`pending` được retry.
    """
    await _save_resume(client)

    pending_job_id = await _create_job("Job pending - chua tung phan tich")

    failed_job_id = await _create_job("Job failed - loi ky thuat that")
    async with SessionLocal() as session:
        run_repo = AgentRunRepository(session)
        broken_agent = MatchingAgent(client=FakeAnthropicClient(responses=["khong phai json hop le"]))
        with pytest.raises(AgentExecutionError) as exc_info:
            await broken_agent.run(
                AgentContext(resume_text="CV", job_description_text="JD failed", job_id=failed_job_id)
            )
        for log in exc_info.value.run_logs:
            await run_repo.log(run_log=log, job_id=failed_job_id)
        await session.commit()

    needs_review_job_id = await _create_needs_review_job()

    # Xác nhận qua ĐÚNG API thật (không đoán) rằng cả 3 job đang ở đúng 3 trạng thái mong đợi
    # TRƯỚC khi chạy script — nếu bước setup sai, test phải fail ở đây, không phải fail mơ hồ
    # ở assertion cuối.
    history = (await client.get("/api/jobs")).json()
    statuses = {h["job"]["id"]: h["analysis_status"] for h in history}
    assert statuses[pending_job_id] == "pending"
    assert statuses[failed_job_id] == "failed"
    assert statuses[needs_review_job_id] == "needs_review"

    fake_client = fake_agent(responses=[valid_match_json, valid_match_json])
    await run()

    # CHỈ 2 lần gọi (pending + failed) — needs_review KHÔNG được gọi lại.
    assert len(fake_client.calls) == 2
    called_contents = [call["user_content"] for call in fake_client.calls]
    assert not any("JD bat dong that su" in content for content in called_contents)

    assert await _count(MatchResult) == 2
    async with SessionLocal() as session:
        matched_job_ids = {
            m.job_id for m in (await session.execute(select(MatchResult))).scalars().all()
        }
    assert matched_job_ids == {pending_job_id, failed_job_id}
    assert needs_review_job_id not in matched_job_ids

    # needs_review vẫn giữ nguyên trạng thái sau khi chạy script — không bị đụng vào.
    history_after = (await client.get("/api/jobs")).json()
    statuses_after = {h["job"]["id"]: h["analysis_status"] for h in history_after}
    assert statuses_after[needs_review_job_id] == "needs_review"
