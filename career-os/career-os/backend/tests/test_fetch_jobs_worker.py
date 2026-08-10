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
from app.workers.fetch_jobs import (
    build_effective_keywords,
    matches_relevant_keyword,
    passes_level_filter,
    run_fetch_jobs,
)
from app.workers.relevance_keywords import RELEVANT_KEYWORDS

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


# --- Kết hợp từ khóa tĩnh + tự rút từ CV (thuần, không mock) — Phase 3 việc #4 mục 6 -----


class TestBuildEffectiveKeywords:
    def test_includes_both_static_and_dynamic(self):
        keywords = build_effective_keywords(["PyTorch", "computer vision"])
        assert "PyTorch" in keywords
        assert "computer vision" in keywords
        assert "data engineering" in keywords  # từ RELEVANT_KEYWORDS tĩnh

    def test_duplicate_keyword_not_repeated(self):
        # "robotics" đã có sẵn trong RELEVANT_KEYWORDS tĩnh.
        keywords = build_effective_keywords(["robotics", "PyTorch"])
        assert keywords.count("robotics") == 1

    def test_empty_dynamic_keywords_returns_static_only(self):
        keywords = build_effective_keywords([])
        assert set(keywords) == set(RELEVANT_KEYWORDS)


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
    # Lọc theo agent_name='matching_agent' — scam_detection_agent giờ CŨNG ghi agent_runs độc
    # lập cho cùng job (xem Phase 3 việc #3), không lọc sẽ vỡ scalar_one() (>1 row).
    async with SessionLocal() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.agent_name == "matching_agent"))
        ).scalar_one()
    assert run.error is not None


# --- Kết hợp với cv_extraction_agent trong luồng thật (Phase 3 việc #4 mục 6) -------------


@async_test
async def test_dynamic_keyword_from_cv_extraction_supplements_static_filter(
    client, fake_scraper, fake_agent, fake_cv_extraction_agent, valid_match_json
):
    """Job CHỈ khớp từ khóa tự rút từ CV ("Kubernetes", không có trong RELEVANT_KEYWORDS tĩnh)
    vẫn phải lọt qua lọc — đúng nguyên tắc BỔ SUNG, không thay thế."""
    fake_cv_extraction_agent(responses=['{"domains": [], "key_skills": ["Kubernetes"]}'])
    await _save_resume(client)  # kích hoạt trích xuất thật, lưu cv_extracted_keywords

    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {
            "Data Engineer": [
                _job(
                    "https://itviec.com/it-jobs/dynamic-kw-1",
                    title="Site Reliability Engineer",
                    tags=["Kubernetes"],
                )
            ]
        }
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/dynamic-kw-1"] = "Fresher role, entry level."

    await run_fetch_jobs()

    assert await _count(Job) == 1


@async_test
async def test_no_extracted_keywords_row_falls_back_to_static_only(
    client, fake_scraper, fake_agent, fake_cv_extraction_agent, valid_match_json
):
    """Chưa từng có `cv_extracted_keywords` nào (trích xuất lỗi lúc lưu resume) -> chỉ dùng
    RELEVANT_KEYWORDS tĩnh, không lỗi gì — hành vi y hệt trước khi có tính năng CV extraction."""
    from app.integrations.anthropic import AnthropicCallError

    fake_cv_extraction_agent(raise_error=AnthropicCallError("gia lap loi trich xuat"))
    await _save_resume(client)

    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {"Data Engineer": [_job("https://itviec.com/it-jobs/static-only-1")]}
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/static-only-1"] = "Fresher role, entry level."

    await run_fetch_jobs()

    assert await _count(Job) == 1  # khớp qua "data engineer" tĩnh, không đụng gì tới CV extraction


# --- Lọc rẻ bằng embedding (Phase 3 việc #4 mục 4) -----------------------------------------


def _vec(value: float) -> list[float]:
    from app.integrations.embedding_client import EMBEDDING_DIM

    return [value] * EMBEDDING_DIM


@async_test
async def test_job_with_no_keyword_match_but_high_embedding_similarity_still_passes(
    client, fake_scraper, fake_agent, fake_cv_extraction_agent, fake_embedding_client, valid_match_json
):
    """Job KHÔNG khớp từ khóa nào (cả tĩnh lẫn CV trích xuất) NHƯNG embedding similarity vượt
    ngưỡng -> vẫn lọt qua, đúng logic OR (không phải AND)."""
    resume_text = "random-domain-unrelated-to-keywords"
    title = "Obscure Title Not In Any Keyword List"
    tags = ["ZzzUnmatchedTag"]
    job_text = " ".join([title, *tags])  # đúng cách `run_fetch_jobs()` ghép title+tags
    # Vector GẦN NHAU (similarity=1.0, vượt ngưỡng mặc định 0.25) cho đúng 2 chuỗi cụ thể này —
    # bất kỳ input nào khác gọi embed_text() sẽ raise lỗi rõ ràng (xem fake_embedding_client).
    # Cài TRƯỚC khi lưu resume — resume cũng gọi embed_text() ngay lúc lưu (Phase 3 việc #4 mục
    # 3), phải dùng đúng fake này chứ không phải fake mặc định của `_embedding_slot`.
    fake_embedding_client(vectors={resume_text: _vec(1.0), job_text: _vec(1.0)})

    # domains/key_skills không rỗng -> resume có embedding sau khi lưu.
    fake_cv_extraction_agent(responses=['{"domains": ["random-domain-unrelated-to-keywords"], "key_skills": []}'])
    await _save_resume(client)

    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {"Data Engineer": [_job("https://itviec.com/it-jobs/embedding-only-1", title=title, tags=tags)]}
    )
    fake_scraper["details"]["https://itviec.com/it-jobs/embedding-only-1"] = "Fresher role, entry level."

    await run_fetch_jobs()

    assert await _count(Job) == 1
    async with SessionLocal() as session:
        job = (await session.execute(select(Job))).scalar_one()
    assert job.title == title
    assert list(job.embedding) == pytest.approx(_vec(1.0))  # jobs.embedding được lưu khi insert


@async_test
async def test_job_with_no_keyword_match_and_low_embedding_similarity_is_filtered_out(
    client, fake_scraper, fake_agent, fake_cv_extraction_agent, fake_embedding_client, valid_match_json
):
    resume_text = "random-domain-unrelated-to-keywords"
    title = "Obscure Title Not In Any Keyword List"
    tags = ["ZzzUnmatchedTag"]
    job_text = " ".join([title, *tags])
    # similarity=0.0 (trực giao) < ngưỡng mặc định 0.25 -> KHÔNG lọt qua. Cài TRƯỚC khi lưu
    # resume, cùng lý do như test phía trên.
    fake_embedding_client(vectors={resume_text: [1.0, 0.0] + [0.0] * 766, job_text: [0.0, 1.0] + [0.0] * 766})

    fake_cv_extraction_agent(responses=['{"domains": ["random-domain-unrelated-to-keywords"], "key_skills": []}'])
    await _save_resume(client)

    fake_agent(responses=["unused"])
    fake_scraper["set_categories"](
        {"Data Engineer": [_job("https://itviec.com/it-jobs/embedding-low-1", title=title, tags=tags)]}
    )

    await run_fetch_jobs()

    assert await _count(Job) == 0
    assert fake_scraper["detail_calls"] == []  # bị loại TRƯỚC khi fetch detail


@async_test
async def test_no_resume_embedding_skips_embedding_condition_entirely_no_crash(
    client, fake_scraper, fake_agent, fake_embedding_client, valid_match_json
):
    """`resumes.embedding` là NULL (hành vi mặc định — CV extraction fake trả rỗng, xem
    `_cv_extraction_agent_slot`) -> bỏ hẳn điều kiện embedding cho CẢ LẦN CHẠY, không crash, chỉ
    dùng 2 điều kiện từ khóa như hành vi gốc, và KHÔNG gọi `embed_text()` cho từng job (tiết
    kiệm, không có gì để so sánh)."""
    calls = fake_embedding_client(vectors={})  # bất kỳ lời gọi nào cũng phải raise ngay
    await _save_resume(client)  # CV extraction mặc định trả rỗng -> resume.embedding = NULL

    fake_agent(responses=[valid_match_json])
    fake_scraper["set_categories"](
        {"Data Engineer": [_job("https://itviec.com/it-jobs/no-resume-embedding-1", title="Business Analyst", tags=["Excel"])]}
    )

    await run_fetch_jobs()

    assert await _count(Job) == 0  # không khớp từ khóa, không có embedding để so sánh -> bị loại
    assert calls == []  # embed_text() KHÔNG được gọi cho job này
