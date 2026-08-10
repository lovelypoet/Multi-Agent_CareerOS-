"""Test `scam_detection_agent` — bài toán phân loại có cấu trúc, tái dùng đúng cơ chế
multi-provider + ensemble + `needs_review` đã có ở `matching_agent` (xem
`test_matching_agent_ensemble.py` để đối chiếu style test).

Quan trọng nhất trong file này: test cho bug đã sửa ở mục 0 (Phase 3 việc #3) — `agent_runs` giờ
có 3 agent cùng ghi (`matching_agent`, `cover_letter_agent`, `scam_detection_agent`), mọi query
suy ra trạng thái từ bảng này PHẢI lọc đúng `agent_name`, không được lẫn lộn.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app.agents.scam_detection_agent import ScamDetectionAgent
from app.core.agent_contract import AgentContext
from app.core.db import SessionLocal
from app.models import AgentRun, Job, ScamAssessment
from app.repositories.scam_assessment_repository import ScamAssessmentRepository
from app.schemas.scam_detection import ScamDetectionOutput
from tests.conftest import FakeAnthropicClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _scam_json(
    *, is_suspicious: bool, risk_level: str, red_flags: list[str], reasoning: str = "ly do mac dinh"
) -> str:
    return json.dumps(
        {
            "is_suspicious": is_suspicious,
            "risk_level": risk_level,
            "red_flags": red_flags,
            "reasoning": reasoning,
        }
    )


def _fake_client(model_name: str, *, response: str | None = None, error: Exception | None = None):
    client = FakeAnthropicClient(responses=[response] if response else None, raise_error=error)
    client.model = model_name
    return client


# --- Provider đơn (không ensemble) — trực tiếp gọi agent, không qua API ------------------


async def test_single_provider_clear_scam_case_flagged_high():
    """Case 1 của prompt: nhiều dấu hiệu cùng lúc, đặc biệt có yêu cầu đóng phí -> high."""
    client = FakeAnthropicClient(
        responses=[
            _scam_json(
                is_suspicious=True,
                risk_level="high",
                red_flags=[
                    "Yeu cau dong phi dao tao 500.000d",
                    "Luong 30-50 trieu khong tuong xung voi yeu cau",
                    "Chi lien he qua Zalo ca nhan",
                ],
                reasoning="Nhieu dau hieu lua dao ro rang, dac biet la yeu cau dong phi.",
            )
        ]
    )
    agent = ScamDetectionAgent(client=client)

    result = await agent.run(AgentContext(resume_text="", job_description_text="JD lua dao ro rang"))

    assert result.output["is_suspicious"] is True
    assert result.output["risk_level"] == "high"
    assert len(result.output["red_flags"]) == 3
    assert result.needs_review is False
    assert len(result.run_logs) == 1
    assert result.run_logs[0].error is None


async def test_single_provider_legitimate_job_not_flagged_high():
    """Case 2 của prompt: job thật, có 1-2 đặc điểm bề ngoài dễ nhầm nhưng hợp pháp -> KHÔNG high."""
    client = FakeAnthropicClient(
        responses=[
            _scam_json(
                is_suspicious=False,
                risk_level="low",
                red_flags=[],
                reasoning="Co ten cong ty ro rang, co email cong ty, khong yeu cau dong phi.",
            )
        ]
    )
    agent = ScamDetectionAgent(client=client)

    result = await agent.run(AgentContext(resume_text="", job_description_text="JD sales that"))

    assert result.output["risk_level"] != "high"
    assert result.output["is_suspicious"] is False
    assert result.needs_review is False


async def test_context_does_not_need_resume_text():
    """Khác matching_agent/cover_letter_agent — scam detection không cần resume_text trong
    prompt gửi đi, chỉ cần job_description_text."""
    client = FakeAnthropicClient(
        responses=[_scam_json(is_suspicious=False, risk_level="low", red_flags=[])]
    )
    agent = ScamDetectionAgent(client=client)

    await agent.run(AgentContext(resume_text="", job_description_text="JD_MARKER_XYZ"))

    assert "JD_MARKER_XYZ" in client.calls[0]["user_content"]
    assert "{job_description_text}" not in client.calls[0]["user_content"]


# --- Ensemble — trực tiếp gọi agent, không qua API ---------------------------------------


async def test_ensemble_agreement_picks_result_with_more_red_flags():
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_scam_json(is_suspicious=True, risk_level="high", red_flags=["a", "b"], reasoning="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_scam_json(
            is_suspicious=True, risk_level="high", red_flags=["a", "b", "c"], reasoning="llama"
        ),
    )
    agent = ScamDetectionAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(AgentContext(resume_text="", job_description_text="JD"))

    # llama có 3 red_flags > qwen có 2 -> lấy nguyên bản của llama (thận trọng hơn), NGƯỢC
    # hướng với matching (lấy điểm thấp hơn) vì ở đây không có điểm số, tín hiệu thận trọng là
    # số lượng cảnh báo.
    assert result.output["reasoning"] == "llama"
    assert len(result.output["red_flags"]) == 3
    assert result.needs_review is False
    assert len(result.run_logs) == 2


async def test_ensemble_agreement_tie_in_red_flags_count_picks_first():
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_scam_json(is_suspicious=True, risk_level="medium", red_flags=["a"], reasoning="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_scam_json(is_suspicious=True, risk_level="medium", red_flags=["x"], reasoning="llama"),
    )
    agent = ScamDetectionAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(AgentContext(resume_text="", job_description_text="JD"))

    assert result.output["reasoning"] == "qwen"  # hòa số lượng -> lấy kết quả đầu tiên


async def test_ensemble_disagreement_on_risk_level_needs_review():
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_scam_json(is_suspicious=False, risk_level="low", red_flags=[], reasoning="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_scam_json(is_suspicious=True, risk_level="high", red_flags=["x"], reasoning="llama"),
    )
    agent = ScamDetectionAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(AgentContext(resume_text="", job_description_text="JD"))

    assert result.output is None
    assert result.needs_review is True
    assert len(result.run_logs) == 2
    assert all(log.error is None for log in result.run_logs)


async def test_ensemble_disagreement_on_is_suspicious_alone_also_needs_review():
    """Bất đồng ở is_suspicious dù risk_level 'trùng khớp bề ngoài' (không thể xảy ra thật vì
    ràng buộc schema, nhưng ĐÚNG ĐỊNH NGHĨA bất đồng phải xét CẢ 2 field, không chỉ risk_level)."""
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_scam_json(is_suspicious=False, risk_level="low", red_flags=[], reasoning="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_scam_json(is_suspicious=True, risk_level="medium", red_flags=["x"], reasoning="llama"),
    )
    agent = ScamDetectionAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(AgentContext(resume_text="", job_description_text="JD"))

    assert result.needs_review is True


# --- Schema: is_suspicious/risk_level phải nhất quán -------------------------------------


async def test_schema_rejects_inconsistent_is_suspicious_and_risk_level():
    """Không `await` gì (validate là code đồng bộ) — vẫn khai `async def` vì module này áp dụng
    `pytestmark = pytest.mark.asyncio(...)` cho toàn bộ file, khớp loop_scope="session" với các
    file test khác trong suite (xem ghi chú tương tự ở `test_matching_agent_ensemble.py`)."""
    with pytest.raises(Exception):
        ScamDetectionOutput.model_validate(
            {"is_suspicious": False, "risk_level": "high", "red_flags": [], "reasoning": "x"}
        )


async def test_schema_accepts_consistent_low_risk():
    output = ScamDetectionOutput.model_validate(
        {"is_suspicious": False, "risk_level": "low", "red_flags": [], "reasoning": "x"}
    )
    assert output.is_suspicious is False


# --- Tích hợp qua API thật: POST /api/jobs/analyze ---------------------------------------


async def _save_resume(client, content: str = "3 nam React, TypeScript co ban.") -> None:
    response = await client.post("/api/resume", json={"content": content})
    assert response.status_code == 200


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _create_job(description: str = "JD bat ky") -> int:
    async with SessionLocal() as session:
        job = Job(description=description)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


async def test_ensemble_consensus_saves_scam_assessment_via_real_endpoint(
    client, fake_agent, fake_scam_agent, valid_match_json
):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_scam_json(is_suspicious=True, risk_level="high", red_flags=["a"], reasoning="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_scam_json(is_suspicious=True, risk_level="high", red_flags=["a", "b"], reasoning="llama"),
    )
    fake_scam_agent(ensemble_clients=[client_a, client_b])

    response = await client.post("/api/jobs/analyze", json={"description": "JD bat ky"})

    assert response.status_code == 201
    assert await _count(ScamAssessment) == 1

    async with SessionLocal() as session:
        assessment = (await session.execute(select(ScamAssessment))).scalar_one()
    assert assessment.risk_level == "high"
    assert assessment.is_suspicious is True
    assert assessment.reasoning == "llama"  # nhiều red_flags hơn


async def test_ensemble_disagreement_skips_scam_assessment_via_real_endpoint(
    client, fake_agent, fake_scam_agent, valid_match_json
):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_scam_json(is_suspicious=False, risk_level="low", red_flags=[], reasoning="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_scam_json(is_suspicious=True, risk_level="high", red_flags=["a"], reasoning="llama"),
    )
    fake_scam_agent(ensemble_clients=[client_a, client_b])

    response = await client.post("/api/jobs/analyze", json={"description": "JD bat ky"})

    assert response.status_code == 201
    job_id = response.json()["job"]["id"]
    assert await _count(ScamAssessment) == 0

    async with SessionLocal() as session:
        runs = (
            await session.execute(
                select(AgentRun).where(
                    AgentRun.job_id == job_id, AgentRun.agent_name == "scam_detection_agent"
                )
            )
        ).scalars().all()
    assert len(runs) == 2
    assert all(r.error is None for r in runs)

    # scam bất đồng KHÔNG được ảnh hưởng tới matching — matching vẫn 'analyzed' bình thường.
    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["scam_check_status"] == "needs_review"
    assert item["scam"] is None
    assert item["analysis_status"] == "analyzed"
    assert item["match"] is not None


async def test_scam_failure_does_not_block_matching(client, fake_agent, fake_scam_agent, valid_match_json):
    """Đúng mục 5: 1 agent lỗi không được cản agent còn lại — scam lỗi hoàn toàn, matching vẫn
    chạy và lưu match_result bình thường."""
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    fake_scam_agent(responses=["day khong phai JSON hop le"])

    response = await client.post("/api/jobs/analyze", json={"description": "JD bat ky"})

    assert response.status_code == 201
    body = response.json()
    assert body["match"] is not None  # matching không bị ảnh hưởng bởi scam lỗi
    assert await _count(ScamAssessment) == 0

    job_id = body["job"]["id"]
    async with SessionLocal() as session:
        scam_run = (
            await session.execute(
                select(AgentRun).where(
                    AgentRun.job_id == job_id, AgentRun.agent_name == "scam_detection_agent"
                )
            )
        ).scalar_one()
    assert scam_run.error is not None

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["scam_check_status"] == "failed"
    assert item["analysis_status"] == "analyzed"  # không lây lỗi từ scam sang matching


async def test_reanalyzing_scam_overwrites_previous_assessment_not_duplicates():
    """Đúng mục 9 (KHÔNG làm): scam_assessments KHÔNG giữ lịch sử nhiều lần như match_results/
    cover_letters — upsert theo job_id, phân tích lại ghi đè, không tạo row thứ 2."""
    job_id = await _create_job()

    async with SessionLocal() as session:
        await ScamAssessmentRepository(session).upsert(
            job_id=job_id,
            output=ScamDetectionOutput(
                is_suspicious=True, risk_level="high", red_flags=["a"], reasoning="lan 1"
            ),
        )
        await session.commit()

    assert await _count(ScamAssessment) == 1

    async with SessionLocal() as session:
        await ScamAssessmentRepository(session).upsert(
            job_id=job_id,
            output=ScamDetectionOutput(
                is_suspicious=False, risk_level="low", red_flags=[], reasoning="lan 2"
            ),
        )
        await session.commit()

    assert await _count(ScamAssessment) == 1  # vẫn 1 row, không tạo thêm

    async with SessionLocal() as session:
        assessment = (
            await session.execute(select(ScamAssessment).where(ScamAssessment.job_id == job_id))
        ).scalar_one()
    assert assessment.reasoning == "lan 2"
    assert assessment.risk_level == "low"


# --- Test quan trọng nhất: KHÔNG lẫn lộn giữa các agent khi tính status (mục 0) ----------


async def test_analysis_status_and_scam_check_status_not_confused_by_cover_letter_agent_runs(client):
    """Tạo 1 job có CẢ matching_agent VÀ cover_letter_agent đều đã ghi agent_runs — cover_letter
    output KHÔNG có field 'verdict' lẫn 'risk_level', và có lỗi riêng của nó. Xác nhận
    analysis_status/scam_check_status tính đúng, không bị ảnh hưởng bởi lỗi/dữ liệu của agent
    không liên quan.
    """
    job_id = await _create_job()

    async with SessionLocal() as session:
        session.add_all(
            [
                AgentRun(
                    job_id=job_id,
                    agent_name="matching_agent",
                    prompt_version="matching_v1",
                    model="claude-sonnet-5",
                    output={"score": 70, "verdict": "good_match"},
                    error=None,
                ),
                AgentRun(
                    job_id=job_id,
                    agent_name="cover_letter_agent",
                    prompt_version="cover_letter_v1",
                    model="claude-sonnet-5",
                    output=None,
                    error="loi gia lap cua cover_letter_agent, KHONG lien quan gi matching/scam",
                ),
            ]
        )
        await session.commit()

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)

    # matching: 1 lần chạy thành công nhưng chưa có match_result, chưa đủ 2 verdict khác nhau
    # để needs_review -> 'pending'. QUAN TRỌNG: KHÔNG được thành 'failed' vì lỗi của
    # cover_letter_agent — đây chính là bug đã sửa ở mục 0.
    assert item["analysis_status"] == "pending"

    # scam: CHƯA từng chạy (không có agent_runs nào tên scam_detection_agent) -> 'pending'.
    # QUAN TRỌNG: KHÔNG được thành 'failed' vì lỗi của cover_letter_agent.
    assert item["scam_check_status"] == "pending"
    assert item["scam"] is None


async def test_agent_runs_endpoint_filters_by_agent_name(client):
    """Mục 7: job có CẢ agent_runs của matching lẫn scam_detection — filter đúng agent_name chỉ
    trả row của agent đó; không truyền param trả toàn bộ như hành vi cũ."""
    job_id = await _create_job()

    async with SessionLocal() as session:
        session.add_all(
            [
                AgentRun(
                    job_id=job_id,
                    agent_name="matching_agent",
                    prompt_version="matching_v1",
                    output={"score": 70, "verdict": "good_match"},
                    error=None,
                ),
                AgentRun(
                    job_id=job_id,
                    agent_name="scam_detection_agent",
                    prompt_version="scam_detection_v1",
                    output={
                        "is_suspicious": True,
                        "risk_level": "high",
                        "red_flags": ["x"],
                        "reasoning": "y",
                    },
                    error=None,
                ),
            ]
        )
        await session.commit()

    filtered = await client.get(
        f"/api/jobs/{job_id}/agent-runs", params={"agent_name": "scam_detection_agent"}
    )
    assert filtered.status_code == 200
    filtered_body = filtered.json()
    assert len(filtered_body) == 1
    assert filtered_body[0]["prompt_version"] == "scam_detection_v1"

    unfiltered = await client.get(f"/api/jobs/{job_id}/agent-runs")
    assert unfiltered.status_code == 200
    assert len(unfiltered.json()) == 2


async def test_agent_runs_endpoint_unknown_agent_name_returns_empty_list(client):
    job_id = await _create_job()
    async with SessionLocal() as session:
        session.add(
            AgentRun(
                job_id=job_id,
                agent_name="matching_agent",
                prompt_version="matching_v1",
                output={"score": 70, "verdict": "good_match"},
                error=None,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/jobs/{job_id}/agent-runs", params={"agent_name": "khong_ton_tai_agent"}
    )
    assert response.status_code == 200
    assert response.json() == []
