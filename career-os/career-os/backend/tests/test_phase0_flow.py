"""Kiểm tra các tiêu chí "xong Phase 0" và những quy tắc dễ làm sai nhất."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.integrations.anthropic import AnthropicCallError
from app.models import AgentRun, Job, MatchResult, Resume

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _save_resume(client, content: str = "3 năm kinh nghiệm React, TypeScript cơ bản."):
    return await client.post("/api/resume", json={"content": content})


# --- Resume: phải là upsert, không được tích tụ row -----------------------------


async def test_resume_saved_many_times_stays_one_row(client):
    for i in range(4):
        response = await _save_resume(client, f"resume version {i}")
        assert response.status_code == 200

    assert await _count(Resume) == 1

    async with SessionLocal() as session:
        resume = (await session.execute(select(Resume))).scalar_one()
    assert resume.id == 1
    assert resume.content == "resume version 3"


async def test_resume_rejects_blank_content(client):
    assert (await client.post("/api/resume", json={"content": "   "})).status_code == 422
    assert (await client.post("/api/resume", json={"content": ""})).status_code == 422


async def test_get_resume_404_before_any_save(client):
    response = await client.get("/api/resume")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RESUME_NOT_FOUND"


# --- Analyze: đường đi thành công ----------------------------------------------


async def test_analyze_without_resume_returns_clear_error(client, fake_agent):
    fake_agent(responses=["unused"])
    response = await client.post("/api/jobs/analyze", json={"description": "Tuyển React dev"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RESUME_NOT_FOUND"
    # Không được tạo job rác khi chưa có resume.
    assert await _count(Job) == 0


async def test_analyze_happy_path(client, fake_agent, valid_match_json):
    await _save_resume(client)
    fake_client = fake_agent(responses=[valid_match_json])

    response = await client.post(
        "/api/jobs/analyze", json={"description": "Cần React 3+ năm, TypeScript"}
    )
    assert response.status_code == 201
    body = response.json()

    assert body["match"]["score"] == 72
    assert body["match"]["verdict"] == "good_match"
    assert body["match"]["matched_requirements"] == ["React 3+ năm"]
    assert body["match"]["job_id"] == body["job"]["id"]
    assert body["job"]["title"] is None and body["job"]["company"] is None

    # Prompt thật sự được ghép từ file .md, có cả resume lẫn JD.
    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert "technical recruiter" in call["system"]
    assert "3 năm kinh nghiệm React" in call["user_content"]
    assert "Cần React 3+ năm" in call["user_content"]
    assert "{resume_text}" not in call["user_content"]

    assert await _count(Job) == 1
    assert await _count(MatchResult) == 1


async def test_agent_run_logged_with_usage(client, fake_agent, valid_match_json):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    await client.post("/api/jobs/analyze", json={"description": "JD bất kỳ"})

    async with SessionLocal() as session:
        run = (await session.execute(select(AgentRun))).scalar_one()

    assert run.agent_name == "matching_agent"
    assert run.prompt_version == "matching_v1"
    assert run.input_tokens == 1234
    assert run.output_tokens == 567
    assert run.latency_ms == 42
    assert run.error is None
    assert run.output["score"] == 72
    assert run.job_id is not None


async def test_model_wrapping_json_in_code_fence_is_parsed(client, fake_agent, valid_match_json):
    await _save_resume(client)
    fake_agent(responses=[f"Đây là kết quả:\n```json\n{valid_match_json}\n```\nHết."])

    response = await client.post("/api/jobs/analyze", json={"description": "JD"})
    assert response.status_code == 201
    assert response.json()["match"]["score"] == 72


# --- Analyze: đường đi thất bại -------------------------------------------------


async def test_unparseable_output_saves_job_and_error_but_no_match_row(client, fake_agent):
    await _save_resume(client)
    fake_agent(responses=["Xin lỗi, tôi không thể trả lời dạng JSON."])

    response = await client.post("/api/jobs/analyze", json={"description": "JD lỗi"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "AGENT_FAILED"

    # Job vẫn được giữ lại (lưu trước khi gọi AI), nhưng không có dữ liệu rác trong match_results.
    assert await _count(Job) == 1
    assert await _count(MatchResult) == 0

    async with SessionLocal() as session:
        run = (await session.execute(select(AgentRun))).scalar_one()
    assert run.error is not None
    assert run.output is None


async def test_output_with_wrong_schema_is_rejected(client, fake_agent):
    await _save_resume(client)
    # verdict sai giá trị + score ngoài khoảng cho phép.
    fake_agent(responses=['{"score": 150, "verdict": "perfect", "reasoning": "x"}'])

    response = await client.post("/api/jobs/analyze", json={"description": "JD"})
    assert response.status_code == 502
    assert await _count(MatchResult) == 0

    async with SessionLocal() as session:
        run = (await session.execute(select(AgentRun))).scalar_one()
    assert "schema" in (run.error or "").lower()


async def test_anthropic_api_error_is_logged_and_reported(client, fake_agent):
    await _save_resume(client)
    fake_agent(raise_error=AnthropicCallError("rate limit"))

    response = await client.post("/api/jobs/analyze", json={"description": "JD"})
    assert response.status_code == 502
    # Không lộ chi tiết kỹ thuật ra ngoài message hiển thị cho user.
    assert "rate limit" not in response.json()["detail"]["message"]

    async with SessionLocal() as session:
        run = (await session.execute(select(AgentRun))).scalar_one()
    assert "rate limit" in run.error


async def test_empty_description_rejected_before_touching_db(client, fake_agent):
    await _save_resume(client)
    fake_agent(responses=["unused"])

    assert (await client.post("/api/jobs/analyze", json={"description": "   "})).status_code == 422
    assert await _count(Job) == 0


# --- Lịch sử ---------------------------------------------------------------------


async def test_history_empty_returns_empty_array(client):
    response = await client.get("/api/jobs")
    assert response.status_code == 200
    assert response.json() == []


async def test_history_newest_first_with_latest_match(client, fake_agent, valid_match_json):
    await _save_resume(client)
    low = valid_match_json.replace('"score": 72', '"score": 30').replace(
        '"verdict": "good_match"', '"verdict": "weak_match"'
    )
    fake_agent(responses=[valid_match_json, low])

    first = await client.post("/api/jobs/analyze", json={"description": "JD một"})
    second = await client.post("/api/jobs/analyze", json={"description": "JD hai"})
    assert first.status_code == 201 and second.status_code == 201

    history = (await client.get("/api/jobs")).json()
    assert len(history) == 2
    assert history[0]["job"]["description"] == "JD hai"
    assert history[0]["match"]["score"] == 30
    assert history[1]["match"]["score"] == 72


async def test_history_includes_job_whose_analysis_failed(client, fake_agent):
    await _save_resume(client)
    fake_agent(responses=["không phải json"])
    await client.post("/api/jobs/analyze", json={"description": "JD hỏng"})

    history = (await client.get("/api/jobs")).json()
    assert len(history) == 1
    assert history[0]["match"] is None


async def test_history_shows_only_latest_match_per_job(client, fake_agent, valid_match_json):
    """Nếu 1 job có nhiều match_result, danh sách chỉ được trả về đúng bản mới nhất."""
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    response = await client.post("/api/jobs/analyze", json={"description": "JD"})
    job_id = response.json()["job"]["id"]

    async with SessionLocal() as session:
        session.add(
            MatchResult(
                job_id=job_id,
                resume_id=1,
                score=91,
                verdict="strong_match",
                reasoning="Bản phân tích lại, mới hơn.",
                matched_requirements=[],
                missing_requirements=[],
                suggestions=[],
            )
        )
        await session.commit()

    history = (await client.get("/api/jobs")).json()
    assert len(history) == 1, "1 job không được xuất hiện 2 lần trong lịch sử"
    assert history[0]["match"]["score"] == 91
