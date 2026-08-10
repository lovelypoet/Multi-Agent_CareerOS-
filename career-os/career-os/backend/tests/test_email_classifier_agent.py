"""Test `email_classifier_agent` — bài toán phân loại có cấu trúc, tái dùng đúng cơ chế
multi-provider + ensemble + `needs_review` đã có ở `matching_agent`/`scam_detection_agent` (xem
2 file test tương ứng để đối chiếu style).
"""

from __future__ import annotations

import json

import pytest

from app.agents.email_classifier_agent import EmailClassifierAgent
from app.core.agent_contract import AgentContext
from app.schemas.email_notification import EmailClassificationOutput
from tests.conftest import FakeAnthropicClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _email_json(
    *,
    is_relevant: bool,
    category: str | None,
    company_name_mentioned: str | None = None,
    summary: str = "tom tat mac dinh",
) -> str:
    return json.dumps(
        {
            "is_relevant": is_relevant,
            "category": category,
            "company_name_mentioned": company_name_mentioned,
            "summary": summary,
        }
    )


def _fake_client(model_name: str, *, response: str | None = None, error: Exception | None = None):
    client = FakeAnthropicClient(responses=[response] if response else None, raise_error=error)
    client.model = model_name
    return client


def _context(sender: str = "hr@abc.com", subject: str = "Sub", body_text: str = "Body") -> AgentContext:
    return AgentContext(
        resume_text="",
        job_description_text="",
        metadata={"sender": sender, "subject": subject, "body_text": body_text},
    )


# --- Provider đơn (không ensemble) -------------------------------------------------------


async def test_single_provider_interview_invite():
    client = FakeAnthropicClient(
        responses=[
            _email_json(
                is_relevant=True,
                category="interview_invite",
                company_name_mentioned="ABC Tech",
                summary="Moi phong van ngay 15/08.",
            )
        ]
    )
    agent = EmailClassifierAgent(client=client)

    result = await agent.run(_context())

    assert result.output["is_relevant"] is True
    assert result.output["category"] == "interview_invite"
    assert result.output["company_name_mentioned"] == "ABC Tech"
    assert result.needs_review is False


async def test_single_provider_not_relevant_marketing_email():
    client = FakeAnthropicClient(
        responses=[_email_json(is_relevant=False, category=None, summary="Email marketing, khong lien quan.")]
    )
    agent = EmailClassifierAgent(client=client)

    result = await agent.run(_context(subject="Uu dai ung tuyen thanh vien Shopee Xu"))

    assert result.output["is_relevant"] is False
    assert result.output["category"] is None
    assert result.needs_review is False


async def test_context_uses_metadata_not_job_description_text():
    """Agent này KHÔNG có resume_text/job_description_text — nội dung email truyền qua
    metadata."""
    client = FakeAnthropicClient(
        responses=[_email_json(is_relevant=False, category=None, summary="x")]
    )
    agent = EmailClassifierAgent(client=client)

    await agent.run(_context(sender="MARKER_SENDER", subject="MARKER_SUBJECT", body_text="MARKER_BODY"))

    sent = client.calls[0]["user_content"]
    assert "MARKER_SENDER" in sent and "MARKER_SUBJECT" in sent and "MARKER_BODY" in sent


# --- Ensemble ------------------------------------------------------------------------------


async def test_ensemble_agreement_picks_first_result():
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_email_json(is_relevant=True, category="rejection", summary="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_email_json(is_relevant=True, category="rejection", summary="llama"),
    )
    agent = EmailClassifierAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(_context())

    # Đồng thuận, không có tín hiệu định lượng để xếp hạng -> lấy kết quả ĐẦU TIÊN.
    assert result.output["summary"] == "qwen"
    assert result.needs_review is False
    assert len(result.run_logs) == 2


async def test_ensemble_disagreement_on_category_needs_review():
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_email_json(is_relevant=True, category="rejection", summary="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_email_json(is_relevant=True, category="interview_invite", summary="llama"),
    )
    agent = EmailClassifierAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(_context())

    assert result.output is None
    assert result.needs_review is True
    assert len(result.run_logs) == 2
    assert all(log.error is None for log in result.run_logs)


async def test_ensemble_disagreement_on_is_relevant_needs_review():
    client_a = _fake_client(
        "qwen2.5:7b",
        response=_email_json(is_relevant=False, category=None, summary="qwen"),
    )
    client_b = _fake_client(
        "llama3.1:8b",
        response=_email_json(is_relevant=True, category="other_relevant", summary="llama"),
    )
    agent = EmailClassifierAgent(ensemble_clients=[client_a, client_b])

    result = await agent.run(_context())

    assert result.needs_review is True


# --- Schema: category phải nhất quán với is_relevant --------------------------------------


async def test_schema_rejects_category_when_not_relevant():
    with pytest.raises(Exception):
        EmailClassificationOutput.model_validate(
            {"is_relevant": False, "category": "rejection", "company_name_mentioned": None, "summary": "x"}
        )


async def test_schema_rejects_missing_category_when_relevant():
    with pytest.raises(Exception):
        EmailClassificationOutput.model_validate(
            {"is_relevant": True, "category": None, "company_name_mentioned": None, "summary": "x"}
        )


async def test_schema_accepts_consistent_relevant_output():
    output = EmailClassificationOutput.model_validate(
        {
            "is_relevant": True,
            "category": "follow_up_question",
            "company_name_mentioned": "XYZ",
            "summary": "Can tra loi cau hoi ve muc luong mong muon.",
        }
    )
    assert output.category == "follow_up_question"
