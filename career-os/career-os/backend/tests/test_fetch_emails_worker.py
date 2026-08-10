"""Test worker Phase 3 việc #1 (`workers/fetch_emails.py`) — lọc cổ điển, dedup theo cặp
(account_email, gmail_message_id), đối chiếu company_name -> job_id, cách ly lỗi per-email/
per-account. Dùng fake Gmail client + fake email_classifier_agent, KHÔNG gọi Gmail/LLM thật —
cùng triết lý FakeAnthropicClient/fake_scraper đã dùng ở Phase 0/1.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.integrations.gmail_client import GmailAuthError, GmailFetchError, GmailMessageSummary
from app.models import AgentRun, EmailNotification, Job
from app.workers import fetch_emails
from app.workers.fetch_emails import matches_classic_filter, resolve_job_id, run_fetch_emails

async_test = pytest.mark.asyncio(loop_scope="session")


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _create_job(description: str = "JD bat ky", company: str | None = None) -> int:
    async with SessionLocal() as session:
        job = Job(description=description, company=company)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


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


def _summary(
    message_id: str,
    *,
    sender: str = "hr@abc.com",
    subject: str = "Interview",
    snippet: str = "noi dung ngan",
    received_at: datetime | None = None,
) -> GmailMessageSummary:
    return GmailMessageSummary(
        message_id=message_id,
        sender=sender,
        subject=subject,
        snippet=snippet,
        received_at=received_at or datetime.now(timezone.utc),
    )


# --- Fake Gmail client + settings override -----------------------------------------------


@pytest.fixture
def fake_gmail(monkeypatch):
    state = {
        "summaries": {},  # account_email -> list[GmailMessageSummary] | Exception
        "bodies": {},  # message_id -> str | Exception
        "get_body_calls": [],
        "list_calls": [],
    }

    class _FakeGmailClient:
        def __init__(self, *, account_email: str, token_path):
            self.account_email = account_email
            self.token_path = token_path

        def list_message_summaries_since(self, since):
            state["list_calls"].append((self.account_email, since))
            result = state["summaries"].get(self.account_email, [])
            if isinstance(result, Exception):
                raise result
            return result

        def get_message_body(self, message_id):
            state["get_body_calls"].append(message_id)
            result = state["bodies"].get(message_id, "noi dung day du")
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(fetch_emails, "GmailClient", _FakeGmailClient)

    state["set_summaries"] = lambda account_email, value: state["summaries"].__setitem__(account_email, value)
    state["set_body"] = lambda message_id, value: state["bodies"].__setitem__(message_id, value)
    return state


@pytest.fixture
def fake_gmail_settings(monkeypatch):
    from app.core.config import get_settings

    def _install(*, accounts: list[str], initial_lookback_days: int = 7):
        settings = get_settings().model_copy(
            update={
                "gmail_account_emails": ",".join(accounts),
                "gmail_initial_lookback_days": initial_lookback_days,
            }
        )
        monkeypatch.setattr(fetch_emails, "get_settings", lambda: settings)
        return settings

    return _install


# --- matches_classic_filter / resolve_job_id — hàm thuần, không đụng DB -------------------


class TestMatchesClassicFilter:
    def test_generic_keyword_matches(self):
        assert matches_classic_filter(
            sender="a@b.com", subject="Thu moi interview", snippet="", company_names=[]
        )

    def test_company_name_matches(self):
        assert matches_classic_filter(
            sender="a@b.com", subject="Cap nhat tu ABC Corp", snippet="", company_names=["ABC Corp"]
        )

    def test_no_match_at_all_rejected(self):
        assert not matches_classic_filter(
            sender="noreply@shopee.vn", subject="Sieu sale hom nay", snippet="Giam gia 50%",
            company_names=["ABC Corp"],
        )

    def test_looseness_consistent_with_job_id_resolution(self):
        """Mục 3: `jobs.company` = "Công ty TNHH ABC" (dài), email chỉ ghi "ABC" (ngắn, 1 phần)
        trong tiêu đề — PHẢI vẫn lọt qua bộ lọc cổ điển, không bị loại vì so khớp quá chặt."""
        assert matches_classic_filter(
            sender="hr@abc.com", subject="ABC", snippet="", company_names=["Công ty TNHH ABC"]
        )


class TestResolveJobId:
    def test_unique_match_returns_job_id(self):
        pairs = [(1, "Công ty TNHH ABC"), (2, "XYZ Corp")]
        assert resolve_job_id("ABC", pairs) == 1

    def test_no_match_returns_none(self):
        pairs = [(1, "Công ty TNHH ABC")]
        assert resolve_job_id("Khong lien quan gi", pairs) is None

    def test_none_company_name_returns_none(self):
        pairs = [(1, "Công ty TNHH ABC")]
        assert resolve_job_id(None, pairs) is None

    def test_multiple_matches_returns_none_not_a_guess(self):
        """Công ty có 2 job trong DB — KHÔNG được tự chọn đại 1 job."""
        pairs = [(1, "ABC Technology"), (2, "ABC Solutions")]
        assert resolve_job_id("ABC", pairs) is None


# --- Worker end-to-end ---------------------------------------------------------------------


@async_test
async def test_no_accounts_configured_is_a_noop(fake_gmail_settings, fake_email_classifier_agent):
    fake_gmail_settings(accounts=[])
    fake_client = fake_email_classifier_agent(responses=["unused"])

    await run_fetch_emails()

    assert fake_client.calls == []
    assert await _count(EmailNotification) == 0


@async_test
async def test_relevant_email_via_keyword_is_classified_and_saved(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"](
        "acc1@gmail.com", [_summary("msg-1", subject="Thu moi interview vi tri Backend")]
    )
    fake_client = fake_email_classifier_agent(
        responses=[_email_json(is_relevant=True, category="interview_invite", company_name_mentioned="ABC")]
    )

    await run_fetch_emails()

    assert len(fake_client.calls) == 1
    assert await _count(EmailNotification) == 1
    async with SessionLocal() as session:
        row = (await session.execute(select(EmailNotification))).scalar_one()
    assert row.is_relevant is True
    assert row.category == "interview_invite"
    assert row.account_email == "acc1@gmail.com"
    assert row.gmail_message_id == "msg-1"


@async_test
async def test_email_not_matching_classic_filter_never_reaches_agent(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"](
        "acc1@gmail.com",
        [_summary("msg-1", sender="noreply@shopee.vn", subject="Sieu sale", snippet="Giam gia soc")],
    )
    fake_client = fake_email_classifier_agent(responses=["unused"])

    await run_fetch_emails()

    assert fake_client.calls == []
    assert await _count(EmailNotification) == 0  # không lưu record cho email bị loại ở lọc cổ điển


@async_test
async def test_company_match_from_jobs_table_passes_classic_filter(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    await _create_job(company="Công ty TNHH ABC")
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    # Subject chỉ ghi "ABC" (viết khác 1 phần so với DB), không chứa GENERIC_KEYWORDS nào.
    fake_gmail["set_summaries"](
        "acc1@gmail.com", [_summary("msg-1", subject="ABC", snippet="", sender="x@abc.com")]
    )
    fake_client = fake_email_classifier_agent(
        responses=[_email_json(is_relevant=True, category="other_relevant", company_name_mentioned="ABC")]
    )

    await run_fetch_emails()

    assert len(fake_client.calls) == 1  # lọt qua lọc cổ điển nhờ khớp company, không bị loại


@async_test
async def test_dedup_same_account_same_message_not_reprocessed(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("msg-1", subject="interview")])
    fake_client = fake_email_classifier_agent(
        responses=[_email_json(is_relevant=True, category="interview_invite")]
    )

    await run_fetch_emails()
    assert await _count(EmailNotification) == 1
    assert len(fake_client.calls) == 1

    # Lần quét sau — CÙNG message_id vẫn nằm trong danh sách trả về (mô phỏng cửa sổ lookback
    # còn chồng lấn) -> KHÔNG được gọi lại agent.
    await run_fetch_emails()
    assert await _count(EmailNotification) == 1
    assert len(fake_client.calls) == 1


@async_test
async def test_is_relevant_false_still_saved_and_prevents_reprocessing(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent, client
):
    """Test QUAN TRỌNG NHẤT — bug dedup đã sửa ở mục 4: email is_relevant=false PHẢI vẫn được
    lưu, và lần quét sau KHÔNG được gọi lại agent cho đúng email đó."""
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("msg-1", subject="Interview ABC")])
    fake_client = fake_email_classifier_agent(
        responses=[_email_json(is_relevant=False, category=None, summary="khong lien quan")]
    )

    await run_fetch_emails()

    assert await _count(EmailNotification) == 1
    async with SessionLocal() as session:
        row = (await session.execute(select(EmailNotification))).scalar_one()
    assert row.is_relevant is False

    # Lần quét sau, cùng batch — KHÔNG được gọi lại agent cho email này.
    await run_fetch_emails()
    assert len(fake_client.calls) == 1  # vẫn đúng 1, không tăng lên 2

    # GET /api/email-notifications KHÔNG được trả về email is_relevant=false này.
    response = await client.get("/api/email-notifications")
    assert response.status_code == 200
    assert response.json() == []


@async_test
async def test_one_email_error_does_not_stop_batch_for_that_account(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"](
        "acc1@gmail.com",
        [
            _summary("msg-broken", subject="interview A"),
            _summary("msg-ok", subject="interview B"),
        ],
    )
    fake_gmail["set_body"]("msg-broken", GmailFetchError("khong lay duoc noi dung"))
    fake_client = fake_email_classifier_agent(
        responses=[_email_json(is_relevant=True, category="interview_invite")]
    )

    await run_fetch_emails()

    assert await _count(EmailNotification) == 1
    async with SessionLocal() as session:
        row = (await session.execute(select(EmailNotification))).scalar_one()
    assert row.gmail_message_id == "msg-ok"


@async_test
async def test_first_run_uses_fixed_lookback_not_max_received_at(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    """Tài khoản CHƯA từng có email_notifications nào — worker phải dùng khoảng lùi cố định
    (gmail_initial_lookback_days), KHÔNG cố lấy MAX(received_at) rồi xử lý NULL sai cách."""
    fake_gmail_settings(accounts=["acc1@gmail.com"], initial_lookback_days=3)
    fake_gmail["set_summaries"]("acc1@gmail.com", [])
    fake_email_classifier_agent(responses=["unused"])

    before = datetime.now(timezone.utc)
    await run_fetch_emails()
    after = datetime.now(timezone.utc)

    assert len(fake_gmail["list_calls"]) == 1
    _, since_used = fake_gmail["list_calls"][0]
    expected_earliest = before - timedelta(days=3, minutes=1)
    expected_latest = after - timedelta(days=3) + timedelta(minutes=1)
    assert expected_earliest <= since_used <= expected_latest


@async_test
async def test_second_run_uses_latest_received_at_for_that_account(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    old_received = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("msg-1", subject="interview", received_at=old_received)])
    fake_email_classifier_agent(responses=[_email_json(is_relevant=True, category="interview_invite")])

    await run_fetch_emails()
    fake_gmail["set_summaries"]("acc1@gmail.com", [])  # lần 2 không có email mới

    await run_fetch_emails()

    assert len(fake_gmail["list_calls"]) == 2
    _, since_second_run = fake_gmail["list_calls"][1]
    # Lùi thêm đúng 1 ngày an toàn so với received_at đã lưu, KHÔNG dùng khoảng lùi cố định nữa.
    assert since_second_run == old_received - timedelta(days=1)


@async_test
async def test_multi_account_one_fails_other_still_processed(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["broken@gmail.com", "ok@gmail.com"])
    fake_gmail["set_summaries"]("broken@gmail.com", GmailAuthError("token het han"))
    fake_gmail["set_summaries"]("ok@gmail.com", [_summary("msg-1", subject="interview")])
    fake_email_classifier_agent(responses=[_email_json(is_relevant=True, category="interview_invite")])

    await run_fetch_emails()

    assert await _count(EmailNotification) == 1
    async with SessionLocal() as session:
        row = (await session.execute(select(EmailNotification))).scalar_one()
    assert row.account_email == "ok@gmail.com"


@async_test
async def test_two_accounts_same_message_id_saved_as_two_separate_rows(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    """Khóa KÉP (account_email, gmail_message_id) — 2 tài khoản trùng message_id vẫn phải lưu
    được cả 2, không đè lên nhau."""
    fake_gmail_settings(accounts=["acc1@gmail.com", "acc2@gmail.com"])
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("same-id", subject="interview")])
    fake_gmail["set_summaries"]("acc2@gmail.com", [_summary("same-id", subject="interview")])
    fake_email_classifier_agent(
        responses=[
            _email_json(is_relevant=True, category="interview_invite"),
            _email_json(is_relevant=True, category="interview_invite"),
        ]
    )

    await run_fetch_emails()

    assert await _count(EmailNotification) == 2
    async with SessionLocal() as session:
        rows = (await session.execute(select(EmailNotification))).scalars().all()
    accounts = {row.account_email for row in rows}
    assert accounts == {"acc1@gmail.com", "acc2@gmail.com"}
    assert all(row.gmail_message_id == "same-id" for row in rows)


@async_test
async def test_worker_leaves_job_id_null_when_company_matches_multiple_jobs(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    """End-to-end cho mục 4: công ty có 2 job trong DB (đã ứng tuyển 2 vị trí khác nhau) —
    email KHÔNG được tự gán vào 1 trong 2, `job_id` phải là NULL, email vẫn được lưu bình
    thường (không phải lỗi)."""
    await _create_job(company="ABC Technology")
    await _create_job(company="ABC Solutions")
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("msg-1", subject="interview")])
    fake_email_classifier_agent(
        responses=[_email_json(is_relevant=True, category="interview_invite", company_name_mentioned="ABC")]
    )

    await run_fetch_emails()

    async with SessionLocal() as session:
        row = (await session.execute(select(EmailNotification))).scalar_one()
    assert row.is_relevant is True
    assert row.job_id is None


@async_test
async def test_worker_resolves_job_id_when_company_matches_exactly_one_job(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    job_id = await _create_job(company="Công ty TNHH ABC")
    await _create_job(company="Hoan toan khong lien quan")
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("msg-1", subject="interview")])
    fake_email_classifier_agent(
        responses=[_email_json(is_relevant=True, category="interview_invite", company_name_mentioned="ABC")]
    )

    await run_fetch_emails()

    async with SessionLocal() as session:
        row = (await session.execute(select(EmailNotification))).scalar_one()
    assert row.job_id == job_id


@async_test
async def test_agent_runs_logged_with_correct_agent_name(
    fake_gmail, fake_gmail_settings, fake_email_classifier_agent
):
    fake_gmail_settings(accounts=["acc1@gmail.com"])
    fake_gmail["set_summaries"]("acc1@gmail.com", [_summary("msg-1", subject="interview")])
    fake_email_classifier_agent(responses=[_email_json(is_relevant=True, category="interview_invite")])

    await run_fetch_emails()

    async with SessionLocal() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.agent_name == "email_classifier_agent"))
        ).scalar_one()
    assert run.prompt_version == "email_classification_v1"
    assert run.job_id is None  # email không tự nhiên gắn với 1 job cụ thể lúc gọi agent
