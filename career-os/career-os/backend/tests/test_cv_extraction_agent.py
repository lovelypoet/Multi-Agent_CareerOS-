"""Test `cv_extraction_agent` — bổ sung (không thay thế) bộ lọc Phase 1. Theo pattern đã có,
dùng fake LLM client, gồm test tích hợp qua endpoint resume thật (POST /api/resume,
POST /api/resume/upload đều tự động chạy agent này ngay sau khi lưu).
"""

from __future__ import annotations

import json

import pytest
from fpdf import FPDF

from app.agents.cv_extraction_agent import CVExtractionAgent
from app.core.agent_contract import AgentContext
from app.integrations.anthropic import AnthropicCallError
from app.integrations.ollama_client import OllamaClient
from app.schemas.cv_extraction import CVExtractionOutput
from tests.conftest import FakeAnthropicClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _cv_json(*, domains: list[str], key_skills: list[str]) -> str:
    return json.dumps({"domains": domains, "key_skills": key_skills})


def _pdf_with_text(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


# --- Agent trực tiếp — đúng 2 test case tham khảo trong cv_extraction_v1.md ---------------


async def test_case1_extracts_specific_skills_over_generic_language_name():
    client = FakeAnthropicClient(
        responses=[_cv_json(domains=["computer vision"], key_skills=["PyTorch", "Docker", "Kubernetes", "AWS"])]
    )
    agent = CVExtractionAgent(client=client)

    result = await agent.run(
        AgentContext(
            resume_text=(
                "3 nam kinh nghiem Python, chuyen ve computer vision - dung PyTorch xay dung va "
                "huan luyen model, trien khai qua Docker va Kubernetes tren AWS."
            ),
            job_description_text="",
        )
    )

    assert result.output["domains"] == ["computer vision"]
    assert set(result.output["key_skills"]) == {"PyTorch", "Docker", "Kubernetes", "AWS"}
    assert "Python" not in result.output["key_skills"]
    assert result.needs_review is False
    assert len(result.run_logs) == 1
    assert result.run_logs[0].error is None


async def test_case2_plumbing_does_not_add_unrelated_output():
    """Test plumbing (fake response cố định) — bản thân việc "không suy diễn" là hành vi của
    PROMPT thật, chỉ verify được bằng tay với model thật (xem test case trong
    cv_extraction_v1.md). Test này verify agent truyền đúng nguyên output của model qua, không
    tự thêm/bớt gì ở tầng code."""
    client = FakeAnthropicClient(responses=[_cv_json(domains=[], key_skills=["Kubernetes"])])
    agent = CVExtractionAgent(client=client)

    result = await agent.run(
        AgentContext(
            resume_text="Co kinh nghiem dung Kubernetes de quan ly container.",
            job_description_text="",
        )
    )

    assert result.output["key_skills"] == ["Kubernetes"]
    assert "Docker" not in result.output["key_skills"]
    assert result.output["domains"] == []


async def test_context_uses_resume_text_only_no_job_description_placeholder_leak():
    client = FakeAnthropicClient(responses=[_cv_json(domains=[], key_skills=[])])
    agent = CVExtractionAgent(client=client)

    await agent.run(AgentContext(resume_text="RESUME_MARKER_XYZ", job_description_text=""))

    sent = client.calls[0]["user_content"]
    assert "RESUME_MARKER_XYZ" in sent
    assert "{resume_text}" not in sent


async def test_ollama_ensemble_provider_still_uses_single_model_not_ensemble(monkeypatch):
    """Agent này KHÔNG BAO GIỜ chạy ensemble dù `settings.llm_provider == "ollama_ensemble"` —
    chỉ dùng `settings.ollama_model`, bỏ qua `ollama_secondary_model` hoàn toàn (xem mục 3:
    không có tiêu chí rõ ràng để so sánh đồng thuận/bất đồng giữa 2 danh sách tự do)."""
    from app.core.config import get_settings

    settings = get_settings().model_copy(update={"llm_provider": "ollama_ensemble"})
    monkeypatch.setattr("app.agents.cv_extraction_agent.get_settings", lambda: settings)

    agent = CVExtractionAgent()

    assert isinstance(agent._client, OllamaClient)
    assert agent._client.model == settings.ollama_model
    assert agent._client.model != settings.ollama_secondary_model


# --- Schema: giới hạn số lượng + dọn phần tử rỗng -----------------------------------------


async def test_schema_rejects_more_than_5_domains():
    with pytest.raises(Exception):
        CVExtractionOutput.model_validate(
            {"domains": ["a", "b", "c", "d", "e", "f"], "key_skills": []}
        )


async def test_schema_rejects_more_than_15_key_skills():
    with pytest.raises(Exception):
        CVExtractionOutput.model_validate(
            {"domains": [], "key_skills": [f"skill{i}" for i in range(16)]}
        )


async def test_schema_drops_empty_items():
    output = CVExtractionOutput.model_validate(
        {"domains": ["data engineering", "", None], "key_skills": ["PyTorch", "   "]}
    )
    assert output.domains == ["data engineering"]
    assert output.key_skills == ["PyTorch"]


async def test_schema_accepts_exactly_5_domains_and_15_key_skills():
    output = CVExtractionOutput.model_validate(
        {"domains": ["a", "b", "c", "d", "e"], "key_skills": [f"skill{i}" for i in range(15)]}
    )
    assert len(output.domains) == 5
    assert len(output.key_skills) == 15


# --- Tích hợp qua endpoint resume thật -----------------------------------------------------


async def test_save_resume_triggers_extraction_and_saves_keywords(client, fake_cv_extraction_agent):
    fake_client = fake_cv_extraction_agent(
        responses=[_cv_json(domains=["computer vision"], key_skills=["PyTorch", "Docker"])]
    )

    response = await client.post("/api/resume", json={"content": "CV noi dung bat ky"})

    assert response.status_code == 200
    assert len(fake_client.calls) == 1

    keywords_response = await client.get("/api/resume/extracted-keywords")
    assert keywords_response.status_code == 200
    body = keywords_response.json()
    assert body["domains"] == ["computer vision"]
    assert body["key_skills"] == ["PyTorch", "Docker"]


async def test_upload_pdf_also_triggers_extraction(client, fake_cv_extraction_agent):
    fake_client = fake_cv_extraction_agent(
        responses=[_cv_json(domains=["backend"], key_skills=["Kubernetes"])]
    )
    content = _pdf_with_text("Kinh nghiem Kubernetes va backend development. " * 3)

    response = await client.post(
        "/api/resume/upload", files={"file": ("cv.pdf", content, "application/pdf")}
    )

    assert response.status_code == 200
    assert len(fake_client.calls) == 1
    keywords = (await client.get("/api/resume/extracted-keywords")).json()
    assert keywords["key_skills"] == ["Kubernetes"]


async def test_extraction_failure_does_not_break_resume_save_or_wipe_old_keywords(
    client, fake_cv_extraction_agent
):
    """Test QUAN TRỌNG NHẤT của file này — lỗi trích xuất KHÔNG được làm hỏng việc lưu resume,
    và KHÔNG được xoá `cv_extracted_keywords` cũ nếu có."""
    fake_cv_extraction_agent(
        responses=[_cv_json(domains=["data engineering"], key_skills=["Airflow"])]
    )
    first = await client.post("/api/resume", json={"content": "CV ban dau"})
    assert first.status_code == 200
    old_keywords = (await client.get("/api/resume/extracted-keywords")).json()
    assert old_keywords["key_skills"] == ["Airflow"]

    fake_cv_extraction_agent(raise_error=AnthropicCallError("loi gia lap, mo phong timeout"))
    second = await client.post("/api/resume", json={"content": "CV cap nhat"})

    assert second.status_code == 200  # PHẢI vẫn thành công
    assert second.json()["content"] == "CV cap nhat"  # resume vẫn được lưu bình thường

    still_old_keywords = (await client.get("/api/resume/extracted-keywords")).json()
    assert still_old_keywords["key_skills"] == ["Airflow"]  # KHÔNG bị xoá


async def test_get_extracted_keywords_404_before_any_save(client):
    response = await client.get("/api/resume/extracted-keywords")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CV_KEYWORDS_NOT_FOUND"


async def test_reextraction_overwrites_not_duplicates(client, fake_cv_extraction_agent):
    """Singleton, không phải append-only — lưu lại resume nhiều lần chỉ giữ đúng 1 bản trích
    xuất mới nhất."""
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import CVExtractedKeywords

    fake_cv_extraction_agent(responses=[_cv_json(domains=["a"], key_skills=["x"])])
    await client.post("/api/resume", json={"content": "Ban 1"})

    fake_cv_extraction_agent(responses=[_cv_json(domains=["b"], key_skills=["y"])])
    await client.post("/api/resume", json={"content": "Ban 2"})

    async with SessionLocal() as session:
        count = (
            await session.execute(select(func.count()).select_from(CVExtractedKeywords))
        ).scalar_one()
    assert count == 1

    keywords = (await client.get("/api/resume/extracted-keywords")).json()
    assert keywords["domains"] == ["b"]
    assert keywords["key_skills"] == ["y"]


# --- Embedding cho resume (Phase 3 việc #4 mục 3) ------------------------------------------


def _vec(value: float) -> list[float]:
    """Vector giả đúng `EMBEDDING_DIM` (768) — cột DB kiểu `VECTOR(768)` từ chối vector sai
    dimension (đã tự verify: lỗi ngay ở tầng DB nếu không đúng), không thể dùng vector ngắn tuỳ ý
    trong test."""
    from app.integrations.embedding_client import EMBEDDING_DIM

    return [value] * EMBEDDING_DIM


async def _resume_embedding():
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import Resume

    async with SessionLocal() as session:
        resume = (await session.execute(select(Resume))).scalar_one()
        return resume.embedding


async def test_extraction_success_with_data_triggers_embedding_with_joined_keywords(
    client, fake_cv_extraction_agent, fake_embedding_client
):
    """Bước 3 đúng thiết kế: input đưa vào `embed_text()` là chuỗi ghép `domains` + `key_skills`
    — assert nội dung THẬT gửi đi, không chỉ assert có gọi hay không."""
    fake_cv_extraction_agent(
        responses=[_cv_json(domains=["computer vision"], key_skills=["PyTorch", "Docker"])]
    )
    calls = fake_embedding_client(vectors={"computer vision, PyTorch, Docker": _vec(0.25)})

    response = await client.post("/api/resume", json={"content": "CV noi dung bat ky"})

    assert response.status_code == 200
    assert calls == ["computer vision, PyTorch, Docker"]
    assert list(await _resume_embedding()) == pytest.approx(_vec(0.25))


async def test_cv_extraction_failure_skips_embedding_and_keeps_old_one(
    client, fake_cv_extraction_agent, fake_embedding_client
):
    """CV extraction THẤT BẠI -> `embed_text()` KHÔNG được gọi, resume vẫn lưu thành công,
    embedding cũ (nếu có) giữ nguyên."""
    fake_cv_extraction_agent(responses=[_cv_json(domains=["data engineering"], key_skills=["Airflow"])])
    calls = fake_embedding_client(vectors={"data engineering, Airflow": _vec(0.75)})
    first = await client.post("/api/resume", json={"content": "CV ban dau"})
    assert first.status_code == 200
    old_embedding = await _resume_embedding()
    assert old_embedding is not None

    fake_cv_extraction_agent(raise_error=AnthropicCallError("gia lap loi trich xuat"))
    second = await client.post("/api/resume", json={"content": "CV cap nhat"})

    assert second.status_code == 200
    assert calls == ["data engineering, Airflow"]  # KHÔNG có lời gọi mới nào ở lần lưu thứ 2
    new_embedding = await _resume_embedding()
    assert list(new_embedding) == pytest.approx(list(old_embedding))  # giữ nguyên embedding cũ


async def test_cv_extraction_success_but_empty_also_skips_embedding(
    client, fake_cv_extraction_agent, fake_embedding_client
):
    """Case dễ bị bỏ sót: CV extraction THÀNH CÔNG nhưng `domains`/`key_skills` đều rỗng (không
    phải lỗi — CV không có gì cụ thể để trích) -> `embed_text()` CŨNG KHÔNG được gọi, cùng hành
    vi giữ nguyên embedding cũ như case lỗi."""
    fake_cv_extraction_agent(responses=[_cv_json(domains=["backend"], key_skills=["Kubernetes"])])
    calls = fake_embedding_client(vectors={"backend, Kubernetes": _vec(0.5)})
    first = await client.post("/api/resume", json={"content": "CV ban dau"})
    assert first.status_code == 200
    old_embedding = await _resume_embedding()
    assert old_embedding is not None

    fake_cv_extraction_agent(responses=[_cv_json(domains=[], key_skills=[])])
    second = await client.post("/api/resume", json={"content": "CV khong co gi cu the"})

    assert second.status_code == 200
    assert calls == ["backend, Kubernetes"]  # không có lời gọi mới nào
    new_embedding = await _resume_embedding()
    assert list(new_embedding) == pytest.approx(list(old_embedding))
