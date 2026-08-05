"""Test worker Phase 1 (`workers/fetch_jobs.py`) — logic lọc từ khóa, lọc level, dedup
(cả trong-1-lần-chạy lẫn giữa các lần chạy), cách ly lỗi per-job/per-category. Dùng fake
scraper + fake agent, không gọi mạng thật — cùng triết lý FakeAnthropicClient của Phase 0.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.integrations.itviec import ItviecFetchError, JobListingMeta
from app.models import AgentRun, Job, MatchResult
from app.workers import fetch_jobs
from app.workers.fetch_jobs import matches_relevant_keyword, passes_level_filter, run_fetch_jobs

# Áp dụng riêng cho từng test async ở cuối file (không dùng module-level pytestmark) vì
# TestMatchesRelevantKeyword/TestPassesLevelFilter bên dưới là test thuần, đồng bộ.
async_test = pytest.mark.asyncio(loop_scope="session")


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _save_resume(client, content: str = "3 nam React, TypeScript co ban."):
    return await client.post("/api/resume", json={"content": content})


def _job(url: str, title: str = "Data Engineer Fresher", company: str = "Acme", tags=None) -> JobListingMeta:
    return JobListingMeta(title=title, company=company, url=url, skill_tags=tags or ["Data Engineer"])


# --- Keyword filter (thuần, không mock) -------------------------------------------------


class TestMatchesRelevantKeyword:
    def test_title_matches(self):
        assert matches_relevant_keyword("Data Engineer Fresher", []) is True

    def test_skill_tag_matches(self):
        assert matches_relevant_keyword("Software Engineer", ["ROS2", "C++"]) is True

    def test_no_match(self):
        assert matches_relevant_keyword("Business Analyst", ["Excel", "SQL"]) is False


# --- Level filter (thuần, không mock) — chỗ dễ bug nhất theo prompt Phase 1 mục 10 -------


class TestPassesLevelFilter:
    def test_fresher_in_title_kept(self):
        assert passes_level_filter("Data Engineer Fresher at Cigro Inc.", "some description") is True

    def test_senior_years_in_description_rejected(self):
        assert passes_level_filter("Data Engineer", "Requires 5+ years of experience") is False

    def test_senior_in_title_rejected(self):
        assert passes_level_filter("Senior Machine Learning Engineer", "") is False

    def test_no_signal_at_all_is_kept(self):
        """Quan trọng nhất: không tín hiệu fresher lẫn senior -> phải GIỮ, không loại."""
        assert (
            passes_level_filter("Embedded Engineer", "Work with C++ and RTOS on automotive projects.") is True
        )

    def test_vietnamese_senior_signal_rejected(self):
        assert passes_level_filter("Data Engineer", "Yêu cầu 3+ năm kinh nghiệm") is False


# --- fake scraper: thay CATEGORY_URLS + fetch_listing/fetch_detail, không gọi mạng thật ---


@pytest.fixture
def fake_scraper(monkeypatch):
    state = {"listings": {}, "details": {}, "detail_calls": [], "listing_calls": []}

    async def fake_fetch_listing(category_url: str):
        state["listing_calls"].append(category_url)
        result = state["listings"].get(category_url, [])
        if isinstance(result, Exception):
            raise result
        return result

    async def fake_fetch_detail(url: str):
        state["detail_calls"].append(url)
        detail = state["details"].get(url)
        if isinstance(detail, Exception):
            raise detail
        return detail if detail is not None else "Mo ta mac dinh, khong co tin hieu level nao ca."

    monkeypatch.setattr(fetch_jobs, "fetch_listing", fake_fetch_listing)
    monkeypatch.setattr(fetch_jobs, "fetch_detail", fake_fetch_detail)

    def _set_categories(categories: dict) -> None:
        """categories: {category_name: list[JobListingMeta] | Exception}. category_name
        đóng vai trò luôn category_url trong test (đơn giản hoá, không cần URL thật)."""
        monkeypatch.setattr(fetch_jobs, "CATEGORY_URLS", {name: name for name in categories})
        state["listings"] = dict(categories)

    state["set_categories"] = _set_categories
    return state


# --- run_fetch_jobs end-to-end --------------------------------------------------------


@async_test
async def test_no_resume_skips_entire_run(client, fake_scraper, fake_agent):
    fake_agent(responses=["unused"])
    fake_scraper["set_categories"]({"Data Engineer": [_job("https://itviec.com/it-jobs/a-1")]})

    await run_fetch_jobs()

    assert await _count(Job) == 0
    assert fake_scraper["listing_calls"] == []  # bail ra trước khi fetch category nào


@async_test
async def test_keyword_filter_skips_irrelevant_job(client, fake_scraper, fake_agent, valid_match_json):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {"Data Engineer": [_job("https://itviec.com/it-jobs/irrelevant-1", title="Business Analyst", tags=["Excel"])]}
    )

    await run_fetch_jobs()

    assert await _count(Job) == 0
    assert fake_scraper["detail_calls"] == []  # không fetch detail cho job bị loại ở bước từ khóa


@async_test
async def test_relevant_fresher_job_is_fetched_and_analyzed(client, fake_scraper, fake_agent, valid_match_json):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"]({"Data Engineer": [_job("https://itviec.com/it-jobs/de-fresher-1")]})
    fake_scraper["details"]["https://itviec.com/it-jobs/de-fresher-1"] = (
        "Fresher role, no years of experience required."
    )

    await run_fetch_jobs()

    assert await _count(Job) == 1
    assert await _count(MatchResult) == 1
    async with SessionLocal() as session:
        job = (await session.execute(select(Job))).scalar_one()
    assert job.source == "itviec"
    assert job.title == "Data Engineer Fresher"
    assert job.url == "https://itviec.com/it-jobs/de-fresher-1"


@async_test
async def test_senior_job_passes_keyword_filter_but_rejected_by_level(
    client, fake_scraper, fake_agent, valid_match_json
):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {"Data Engineer": [_job("https://itviec.com/it-jobs/de-senior-1", title="Senior Data Engineer")]}
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/de-senior-1"] = "Requires 5+ years of experience with Spark."

    await run_fetch_jobs()

    assert await _count(Job) == 0


@async_test
async def test_dedup_across_runs_does_not_refetch_detail_or_call_agent(
    client, fake_scraper, fake_agent, valid_match_json
):
    await _save_resume(client)
    fake_client = fake_agent(responses=[valid_match_json, valid_match_json])
    fake_scraper["set_categories"]({"Data Engineer": [_job("https://itviec.com/it-jobs/dup-1")]})

    await run_fetch_jobs()
    assert await _count(Job) == 1
    assert len(fake_scraper["detail_calls"]) == 1

    await run_fetch_jobs()  # chạy lần 2, cùng job y hệt

    assert await _count(Job) == 1  # không tạo row mới
    assert len(fake_scraper["detail_calls"]) == 1  # không fetch lại detail
    assert len(fake_client.calls) == 1  # không gọi lại agent


@async_test
async def test_dedup_within_same_run_across_categories(client, fake_scraper, fake_agent, valid_match_json):
    """1 job xuất hiện ở 2 category listing khác nhau trong CÙNG 1 lần chạy -> chỉ xử lý 1 lần."""
    await _save_resume(client)
    fake_client = fake_agent(responses=[valid_match_json])
    same_job = _job("https://itviec.com/it-jobs/cross-cat-1", title="Computer Vision Engineer Fresher")
    fake_scraper["set_categories"](
        {
            "Data Engineer": [same_job],
            "AI / Machine Learning Engineer": [same_job],
        }
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/cross-cat-1"] = "Fresher, entry level."

    await run_fetch_jobs()

    assert await _count(Job) == 1
    assert len(fake_scraper["detail_calls"]) == 1
    assert len(fake_client.calls) == 1


@async_test
async def test_one_job_error_does_not_stop_batch(client, fake_scraper, fake_agent, valid_match_json):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {
            "Data Engineer": [
                _job("https://itviec.com/it-jobs/broken-1", title="Data Engineer Fresher A"),
                _job("https://itviec.com/it-jobs/ok-1", title="Data Engineer Fresher B"),
            ]
        }
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/broken-1"] = ItviecFetchError("500 server error")
    fake_scraper["details"]["https://itviec.com/it-jobs/ok-1"] = "Fresher role, entry level."

    await run_fetch_jobs()

    assert await _count(Job) == 1
    async with SessionLocal() as session:
        job = (await session.execute(select(Job))).scalar_one()
    assert job.url == "https://itviec.com/it-jobs/ok-1"


@async_test
async def test_category_fetch_error_does_not_stop_other_categories(
    client, fake_scraper, fake_agent, valid_match_json
):
    await _save_resume(client)
    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {
            "Data Engineer": ItviecFetchError("404 category page not found"),
            "Embedded Engineer": [_job("https://itviec.com/it-jobs/ok-cat-2", title="Embedded Engineer Fresher")],
        }
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/ok-cat-2"] = "Fresher, no experience required."

    await run_fetch_jobs()

    assert await _count(Job) == 1


@async_test
async def test_agent_failure_is_logged_but_job_row_kept(client, fake_scraper, fake_agent):
    await _save_resume(client)
    fake_agent(responses=["not valid json"])
    fake_scraper["set_categories"]({"Data Engineer": [_job("https://itviec.com/it-jobs/agent-fail-1")]})
    fake_scraper["details"]["https://itviec.com/it-jobs/agent-fail-1"] = "Fresher role, entry level."

    await run_fetch_jobs()

    assert await _count(Job) == 1
    assert await _count(MatchResult) == 0
    async with SessionLocal() as session:
        run = (await session.execute(select(AgentRun))).scalar_one()
    assert run.error is not None
