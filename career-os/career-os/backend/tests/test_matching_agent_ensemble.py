"""Test chế độ ensemble của `MatchingAgent` — 2 model độc lập, ĐỒNG THUẬN (cùng verdict) thì
lấy model điểm thấp hơn, BẤT ĐỒNG (khác verdict, bất kỳ mức nào) thì KHÔNG tự chọn
(`output=None`, `needs_review=True`) — dữ liệu test cho thấy đồng thuận/bất đồng dự đoán
đúng/sai tốt hơn hẳn việc luôn lấy điểm thấp hơn.

Dùng lại `FakeAnthropicClient` (conftest.py) cho cả 2 "model" giả — gán `.model` khác nhau để
mô phỏng 2 kiến trúc khác nhau, không gọi Ollama thật.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.agents.matching_agent import MatchingAgent
from app.core.agent_contract import AgentContext, AgentExecutionError
from app.core.db import SessionLocal
from app.integrations.ollama_client import OllamaCallError
from app.models import AgentRun, Job, MatchResult
from tests.conftest import FakeAnthropicClient

# Không test nào ở đây đụng DB, nhưng vẫn phải khớp loop_scope="session" với các file test
# khác trong suite, nếu không sẽ làm hỏng event loop mà engine module-level (conftest.py)
# đang gắn vào — đã tự tay verify bug này ở task Ollama trước.
pytestmark = pytest.mark.asyncio(loop_scope="session")


def _match_json(score: int, verdict: str, reasoning: str = "ly do mac dinh") -> str:
    return (
        f'{{"score": {score}, "verdict": "{verdict}", "reasoning": "{reasoning}", '
        '"matched_requirements": [], "missing_requirements": [], "suggestions": []}'
    )


def _fake_client(model_name: str, *, response: str | None = None, error: Exception | None = None):
    client = FakeAnthropicClient(responses=[response] if response else None, raise_error=error)
    client.model = model_name
    return client


async def test_both_models_agree_result_matches_the_lower_scoring_one_entirely():
    client_a = _fake_client("qwen2.5:7b", response=_match_json(70, "good_match", "ly do cua qwen"))
    client_b = _fake_client("llama3.1:8b", response=_match_json(65, "good_match", "ly do cua llama"))

    agent = MatchingAgent(ensemble_clients=[client_a, client_b])
    result = await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    # Toàn bộ output (kể cả reasoning) phải khớp với model B (điểm thấp hơn) — không phải chỉ
    # lấy con số rồi ghép reasoning của model kia.
    assert result.output["score"] == 65
    assert result.output["verdict"] == "good_match"
    assert result.output["reasoning"] == "ly do cua llama"
    assert result.needs_review is False

    assert len(result.run_logs) == 2
    models_logged = {log.model for log in result.run_logs}
    assert models_logged == {"qwen2.5:7b", "llama3.1:8b"}
    assert all(log.prompt_version == "matching_v1" for log in result.run_logs)
    assert all(log.error is None for log in result.run_logs)


async def test_strong_disagreement_needs_review_no_auto_pick():
    client_a = _fake_client("qwen2.5:7b", response=_match_json(90, "strong_match", "qwen rat tu tin"))
    client_b = _fake_client("llama3.1:8b", response=_match_json(15, "weak_match", "llama rat khat khe"))

    agent = MatchingAgent(ensemble_clients=[client_a, client_b])
    result = await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    assert result.output is None
    assert result.needs_review is True
    assert len(result.run_logs) == 2
    assert all(log.error is None for log in result.run_logs)  # cả 2 chạy thành công, không phải lỗi


async def test_adjacent_band_disagreement_also_needs_review():
    """Bất đồng dù chỉ 1 dải liền kề (good_match vs strong_match) vẫn tính là bất đồng — không
    có ngưỡng "bất đồng nhẹ/nặng" nào cả, đúng theo dữ liệu Case C đã quan sát được."""
    client_a = _fake_client("qwen2.5:7b", response=_match_json(65, "good_match", "qwen than trong"))
    client_b = _fake_client("llama3.1:8b", response=_match_json(85, "strong_match", "llama lac quan"))

    agent = MatchingAgent(ensemble_clients=[client_a, client_b])
    result = await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    assert result.output is None
    assert result.needs_review is True
    assert len(result.run_logs) == 2


async def test_tie_score_picks_first_client_result():
    client_a = _fake_client("qwen2.5:7b", response=_match_json(50, "partial_match", "qwen hoa"))
    client_b = _fake_client("llama3.1:8b", response=_match_json(50, "partial_match", "llama hoa"))

    agent = MatchingAgent(ensemble_clients=[client_a, client_b])
    result = await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    assert result.output["reasoning"] == "qwen hoa"  # hòa -> lấy result đầu tiên


async def test_one_model_fails_other_succeeds_still_produces_result_and_logs_both():
    client_a = _fake_client("qwen2.5:7b", error=OllamaCallError("Khong ket noi duoc Ollama"))
    client_b = _fake_client("llama3.1:8b", response=_match_json(55, "partial_match"))

    agent = MatchingAgent(ensemble_clients=[client_a, client_b])
    result = await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    assert result.output["score"] == 55
    assert result.needs_review is False  # chỉ 1 model thành công -> không có gì để "bất đồng"

    assert len(result.run_logs) == 2
    error_log = next(log for log in result.run_logs if log.model == "qwen2.5:7b")
    success_log = next(log for log in result.run_logs if log.model == "llama3.1:8b")
    assert error_log.error is not None
    assert error_log.output is None
    assert success_log.error is None
    assert success_log.output is not None


async def test_both_models_fail_raises_agent_execution_error_with_both_logs():
    client_a = _fake_client("qwen2.5:7b", error=OllamaCallError("loi model qwen"))
    client_b = _fake_client("llama3.1:8b", error=OllamaCallError("loi model llama"))

    agent = MatchingAgent(ensemble_clients=[client_a, client_b])

    with pytest.raises(AgentExecutionError) as exc_info:
        await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    assert len(exc_info.value.run_logs) == 2
    assert all(log.error is not None for log in exc_info.value.run_logs)
    assert "loi model qwen" in str(exc_info.value)
    assert "loi model llama" in str(exc_info.value)


async def test_single_model_mode_still_returns_exactly_one_run_log():
    """Chế độ 1 model (không ensemble) không bị ảnh hưởng — vẫn đúng 1 run_log như trước."""
    client = _fake_client("fake-single-model", response=_match_json(80, "strong_match"))

    agent = MatchingAgent(client=client)
    result = await agent.run(AgentContext(resume_text="CV", job_description_text="JD"))

    assert len(result.run_logs) == 1
    assert result.run_logs[0].model == "fake-single-model"


# --- Tích hợp qua API thật: POST /api/jobs/analyze + GET /api/jobs + GET .../agent-runs -----


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


@pytest.fixture
def fake_ensemble_agent(monkeypatch):
    """Patch `app.api.jobs.get_agent` để trả về MatchingAgent ensemble với 2 client giả —
    dùng để test luồng thật qua `POST /api/jobs/analyze`, không chỉ gọi thẳng MatchingAgent."""

    def _install(
        *,
        response_a: str | None = None,
        response_b: str | None = None,
        model_a: str = "qwen2.5:7b",
        model_b: str = "llama3.1:8b",
    ):
        client_a = _fake_client(model_a, response=response_a)
        client_b = _fake_client(model_b, response=response_b)
        agent = MatchingAgent(ensemble_clients=[client_a, client_b])
        monkeypatch.setattr("app.api.jobs.get_agent", lambda name: agent)
        return agent

    return _install


async def _save_resume(client, content: str = "3 nam React, TypeScript co ban."):
    return await client.post("/api/resume", json={"content": content})


async def test_ensemble_consensus_creates_match_result_via_real_endpoint(client, fake_ensemble_agent):
    """Regression check: đường đi đồng thuận không bị hỏng bởi thay đổi needs_review."""
    await _save_resume(client)
    fake_ensemble_agent(
        response_a=_match_json(70, "good_match", "qwen"),
        response_b=_match_json(65, "good_match", "llama"),
    )

    response = await client.post("/api/jobs/analyze", json={"description": "JD dong thuan"})

    assert response.status_code == 201
    body = response.json()
    assert body["match"] is not None
    assert body["match"]["score"] == 65
    job_id = body["job"]["id"]

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["analysis_status"] == "analyzed"


async def test_ensemble_disagreement_skips_match_result_via_real_endpoint(client, fake_ensemble_agent):
    await _save_resume(client)
    fake_ensemble_agent(
        response_a=_match_json(65, "good_match", "qwen than trong"),
        response_b=_match_json(85, "strong_match", "llama lac quan"),
    )

    response = await client.post("/api/jobs/analyze", json={"description": "JD bat dong"})

    assert response.status_code == 201
    body = response.json()
    assert body["match"] is None
    job_id = body["job"]["id"]

    assert await _count(MatchResult) == 0

    async with SessionLocal() as session:
        runs = (await session.execute(select(AgentRun).where(AgentRun.job_id == job_id))).scalars().all()
    assert len(runs) == 2
    assert all(run.error is None for run in runs)  # cả 2 model chạy đúng, không phải lỗi

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["analysis_status"] == "needs_review"


# --- analysis_status: 4 trường hợp -----------------------------------------------------


async def test_analysis_status_pending_when_never_analyzed(client):
    job_id = await _create_job()

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["analysis_status"] == "pending"


async def test_analysis_status_analyzed_when_match_result_exists(client):
    await _save_resume(client)  # resume_id=1 phải tồn tại trước (FK RESTRICT trên match_results)
    job_id = await _create_job()
    async with SessionLocal() as session:
        session.add(
            MatchResult(
                job_id=job_id,
                resume_id=1,
                score=70,
                verdict="good_match",
                reasoning="da co ket qua",
                matched_requirements=[],
                missing_requirements=[],
                suggestions=[],
            )
        )
        await session.commit()

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["analysis_status"] == "analyzed"


async def test_analysis_status_failed_when_error_run_and_no_match(client):
    job_id = await _create_job()
    async with SessionLocal() as session:
        session.add(
            AgentRun(
                job_id=job_id,
                agent_name="matching_agent",
                prompt_version="matching_v1",
                model="qwen2.5:7b",
                error="Anthropic API loi 401",
            )
        )
        await session.commit()

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["analysis_status"] == "failed"


async def test_analysis_status_needs_review_when_two_successful_different_verdicts(client):
    job_id = await _create_job()
    async with SessionLocal() as session:
        session.add_all(
            [
                AgentRun(
                    job_id=job_id,
                    agent_name="matching_agent",
                    prompt_version="matching_v1",
                    model="qwen2.5:7b",
                    output={"score": 65, "verdict": "good_match"},
                    error=None,
                ),
                AgentRun(
                    job_id=job_id,
                    agent_name="matching_agent",
                    prompt_version="matching_v1",
                    model="llama3.1:8b",
                    output={"score": 85, "verdict": "strong_match"},
                    error=None,
                ),
            ]
        )
        await session.commit()

    history = (await client.get("/api/jobs")).json()
    item = next(h for h in history if h["job"]["id"] == job_id)
    assert item["analysis_status"] == "needs_review"


# --- GET /api/jobs/{job_id}/agent-runs --------------------------------------------------


async def test_get_job_agent_runs_returns_data_in_order(client):
    job_id = await _create_job()
    async with SessionLocal() as session:
        session.add(
            AgentRun(
                job_id=job_id,
                agent_name="matching_agent",
                prompt_version="matching_v1",
                model="qwen2.5:7b",
                output={"score": 65, "verdict": "good_match"},
                error=None,
            )
        )
        await session.flush()
        session.add(
            AgentRun(
                job_id=job_id,
                agent_name="matching_agent",
                prompt_version="matching_v1",
                model="llama3.1:8b",
                output={"score": 85, "verdict": "strong_match"},
                error=None,
            )
        )
        await session.commit()

    response = await client.get(f"/api/jobs/{job_id}/agent-runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["model"] == "qwen2.5:7b"
    assert body[0]["output"]["score"] == 65
    assert body[1]["model"] == "llama3.1:8b"
    assert body[1]["output"]["score"] == 85


async def test_get_job_agent_runs_empty_list_when_never_run(client):
    job_id = await _create_job()

    response = await client.get(f"/api/jobs/{job_id}/agent-runs")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_job_agent_runs_404_for_unknown_job(client):
    response = await client.get("/api/jobs/999999/agent-runs")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"
