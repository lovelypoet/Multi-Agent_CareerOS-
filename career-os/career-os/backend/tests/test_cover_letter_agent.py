"""Test cover letter agent (`api/cover_letters.py`) — CHỈ tạo được cho job đã approve, tái dùng
`FakeAnthropicClient` (agent này luôn dùng Anthropic, không có chế độ ollama/ollama_ensemble như
`matching_agent`, nên không cần fake Ollama)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import AgentRun, CoverLetter, Job

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _cover_letter_json(text: str = "Kinh gui Quy cong ty, day la thu xin viec.") -> str:
    return f'{{"cover_letter_text": "{text}"}}'


async def _create_job(description: str = "JD bat ky") -> int:
    async with SessionLocal() as session:
        job = Job(description=description)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _approve(client, job_id: int) -> None:
    response = await client.patch(f"/api/jobs/{job_id}/application", json={"status": "approved"})
    assert response.status_code == 200


async def _save_resume(client, content: str = "3 nam React, TypeScript co ban.") -> None:
    response = await client.post("/api/resume", json={"content": content})
    assert response.status_code == 200


# --- Điều kiện kích hoạt: chỉ job đã approve --------------------------------------------


async def test_job_not_approved_returns_400_and_never_calls_agent(client, fake_cover_letter_agent):
    job_id = await _create_job()
    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json()])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "APPLICATION_NOT_APPROVED"
    assert fake_client.calls == []  # không tốn API call cho job chưa approve
    assert await _count(CoverLetter) == 0


async def test_rejected_job_also_returns_400(client, fake_cover_letter_agent):
    job_id = await _create_job()
    response = await client.patch(f"/api/jobs/{job_id}/application", json={"status": "rejected"})
    assert response.status_code == 200
    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json()])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "APPLICATION_NOT_APPROVED"
    assert fake_client.calls == []


async def test_unknown_job_id_returns_404_before_approval_check(client, fake_cover_letter_agent):
    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json()])

    response = await client.post("/api/jobs/999999/cover-letter")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"
    assert fake_client.calls == []


# --- Regression theo đúng pattern analyze_job: approved nhưng chưa có resume ------------


async def test_approved_but_no_resume_returns_400(client, fake_cover_letter_agent):
    job_id = await _create_job()
    await _approve(client, job_id)
    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json()])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RESUME_NOT_FOUND"
    assert fake_client.calls == []
    assert await _count(CoverLetter) == 0


# --- Tạo thành công ----------------------------------------------------------------------


async def test_successful_generation_saves_cover_letter_and_logs_agent_run(
    client, fake_cover_letter_agent
):
    job_id = await _create_job()
    await _approve(client, job_id)
    await _save_resume(client)
    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json("Noi dung thu xin viec.")])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Noi dung thu xin viec."
    assert body["job_id"] == job_id
    assert body["resume_id"] == 1

    assert await _count(CoverLetter) == 1
    assert len(fake_client.calls) == 1

    async with SessionLocal() as session:
        runs = (
            await session.execute(select(AgentRun).where(AgentRun.job_id == job_id))
        ).scalars().all()
    assert len(runs) == 1
    assert runs[0].agent_name == "cover_letter_agent"
    assert runs[0].prompt_version == "cover_letter_v1"
    assert runs[0].error is None


async def test_match_context_built_from_latest_match_result_is_passed_to_agent(
    client, fake_cover_letter_agent
):
    """`match_context` phải phản ánh match_result mới nhất — không phải chuỗi rỗng khi đã có
    kết quả phân tích trước đó."""
    job_id = await _create_job()
    await _approve(client, job_id)
    await _save_resume(client)

    from app.models import MatchResult

    async with SessionLocal() as session:
        session.add(
            MatchResult(
                job_id=job_id,
                resume_id=1,
                score=72,
                verdict="good_match",
                reasoning="Dap ung du must-have chinh.",
                matched_requirements=["React 3+ nam"],
                missing_requirements=[],
                suggestions=[],
            )
        )
        await session.commit()

    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json()])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 201
    user_content = fake_client.calls[0]["user_content"]
    assert "72/100" in user_content
    assert "good_match" in user_content
    assert "React 3+ nam" in user_content


async def test_approved_job_with_zero_match_results_still_succeeds_with_clear_context(
    client, fake_cover_letter_agent
):
    """Edge case Phase 2: Approve độc lập với việc AI phân tích thành công hay không — job có
    thể approved mà KHÔNG có match_result nào (lỗi kỹ thuật, hoặc needs_review do ensemble bất
    đồng). Test này KHÔNG mock lỗi phân tích — đơn giản là không có row nào trong `match_results`
    cho job này, đúng thực tế edge case. Cover letter generation KHÔNG được phép bị chặn bởi việc
    thiếu match_result (tôn trọng quyết định approve của người dùng), và `match_context` gửi cho
    agent phải là 1 câu rõ nghĩa — không phải rỗng, không phải `None`/"None" (đó sẽ là 1 dạng gửi
    rác cho LLM y hệt bug đã sửa ở `prompt_loader.py`)."""
    job_id = await _create_job()
    await _approve(client, job_id)
    await _save_resume(client)

    from sqlalchemy import func, select

    from app.models import MatchResult

    async with SessionLocal() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(MatchResult).where(MatchResult.job_id == job_id)
            )
        ).scalar_one()
    assert count == 0  # xác nhận thật sự không có match_result nào, không phải giả định

    fake_client = fake_cover_letter_agent(responses=[_cover_letter_json()])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 201  # PHẢI thành công, không bị chặn vì thiếu match_result
    assert await _count(CoverLetter) == 1

    user_content = fake_client.calls[0]["user_content"]
    match_context_section = user_content.split(
        "## Kết quả phân tích phù hợp đã có (tham khảo, không copy nguyên văn)"
    )[1].split("## Yêu cầu")[0].strip()

    assert match_context_section != ""
    assert match_context_section.lower() != "none"
    assert "None" not in match_context_section
    assert "Chưa có kết quả phân tích" in match_context_section


# --- Tạo lại: nhiều row/job, GET trả bản mới nhất ---------------------------------------


async def test_regenerate_creates_second_row_and_get_returns_latest(client, fake_cover_letter_agent):
    job_id = await _create_job()
    await _approve(client, job_id)
    await _save_resume(client)

    fake_cover_letter_agent(responses=[_cover_letter_json("Ban dau tien.")])
    first = await client.post(f"/api/jobs/{job_id}/cover-letter")
    assert first.status_code == 201

    fake_cover_letter_agent(responses=[_cover_letter_json("Ban thu hai.")])
    second = await client.post(f"/api/jobs/{job_id}/cover-letter")
    assert second.status_code == 201

    assert await _count(CoverLetter) == 2  # append-only, không ghi đè bản cũ

    latest = await client.get(f"/api/jobs/{job_id}/cover-letter")
    assert latest.status_code == 200
    assert latest.json()["content"] == "Ban thu hai."


# --- GET /api/jobs/{job_id}/cover-letter ------------------------------------------------


async def test_get_returns_404_when_none_created_yet(client):
    job_id = await _create_job()

    response = await client.get(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "COVER_LETTER_NOT_FOUND"


async def test_get_returns_404_for_unknown_job(client):
    response = await client.get("/api/jobs/999999/cover-letter")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"


# --- Agent lỗi -----------------------------------------------------------------------------


async def test_agent_failure_returns_502_and_logs_error_run_without_saving(
    client, fake_cover_letter_agent
):
    job_id = await _create_job()
    await _approve(client, job_id)
    await _save_resume(client)
    fake_cover_letter_agent(responses=["day khong phai JSON hop le"])

    response = await client.post(f"/api/jobs/{job_id}/cover-letter")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "AGENT_FAILED"
    assert await _count(CoverLetter) == 0

    async with SessionLocal() as session:
        runs = (
            await session.execute(select(AgentRun).where(AgentRun.job_id == job_id))
        ).scalars().all()
    assert len(runs) == 1
    assert runs[0].error is not None
