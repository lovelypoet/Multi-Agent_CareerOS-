"""Worker Phase 1 — fetch job mới từ ITviec, lọc, dedup, rồi chạy matching_agent.

Chạy 1 lần/ngày qua APScheduler (xem `app/main.py`), trong CÙNG process backend — không
Redis Queue, không worker process riêng (đúng nguyên tắc Phase 0/1).

Thứ tự lọc BẮT BUỘC cho mỗi job trong 1 category listing:
  1. keyword filter (title + skill tags, không gọi mạng) — loại ngay nếu không khớp
     `RELEVANT_KEYWORDS`.
  2. dedup theo `url` (đối chiếu DB + các job đã thấy TRONG lần chạy này) — loại TRƯỚC khi
     fetch detail, để không tốn request cho job đã biết (kể cả khi job đó xuất hiện ở 2
     category listing khác nhau trong cùng 1 lần chạy).
  3. fetch detail + level filter (title + description) — loại nếu có tín hiệu senior rõ
     ràng; KHÔNG tìm thấy tín hiệu nào (cả tích cực lẫn senior) thì GIỮ, xem
     `relevance_keywords.py`.
  4. insert job (source='itviec') + chạy matching_agent + lưu match_result/agent_runs.

Lỗi ở 1 category (fetch listing lỗi) hoặc 1 job (fetch detail lỗi, agent lỗi) KHÔNG được
làm dừng cả batch — bắt lỗi cục bộ, log, tiếp tục job/category tiếp theo.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.integrations.anthropic import AnthropicConfigError
from app.integrations.itviec import CATEGORY_URLS, ItviecFetchError, JobListingMeta, fetch_detail, fetch_listing
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.match_result_repository import MatchResultRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.match import MatchOutput
from app.workers.relevance_keywords import RELEVANT_KEYWORDS, SENIOR_SIGNALS

logger = logging.getLogger(__name__)

MATCHING_AGENT = "matching_agent"
SOURCE_ITVIEC = "itviec"


def matches_relevant_keyword(title: str, skill_tags: list[str]) -> bool:
    """Bước lọc cổ điển (không AI) — khớp title + skill tags với RELEVANT_KEYWORDS."""
    haystack = " ".join([title, *skill_tags]).lower()
    return any(keyword.lower() in haystack for keyword in RELEVANT_KEYWORDS)


def passes_level_filter(title: str, description: str) -> bool:
    """True = giữ lại. Chỉ loại khi có tín hiệu senior RÕ RÀNG trong title hoặc description.

    Không tìm thấy tín hiệu nào (senior lẫn fresher/junior) vẫn trả True — matching_agent sẽ
    tự đánh giá độ phù hợp kinh nghiệm dựa trên CV thật, đây chỉ là lưới lọc thô để tránh gọi
    AI cho job rõ ràng đòi hỏi senior (xem prompt Phase 1 mục 3).
    """
    haystack = f"{title}\n{description}".lower()
    return not any(signal.lower() in haystack for signal in SENIOR_SIGNALS)


class _CategoryCounts:
    """Đếm số lượng qua từng bước lọc trong 1 category — để log rõ ràng, dễ phát hiện lỗi âm thầm."""

    def __init__(self, category_name: str) -> None:
        self.category_name = category_name
        self.fetched = 0
        self.keyword_passed = 0
        self.new_by_url = 0
        self.level_passed = 0
        self.analyzed_success = 0
        self.analyzed_failed = 0
        # Ensemble bất đồng verdict — KHÔNG phải lỗi (cả 2 model chạy đúng), đếm riêng khỏi
        # analyzed_failed để không lẫn lộn "lỗi thật" với "cần người xem lại".
        self.needs_review = 0

    def log_summary(self) -> None:
        logger.info(
            "[fetch_jobs] %s: fetch được %d job -> qua lọc từ khóa: %d -> job mới (chưa có url): "
            "%d -> qua lọc level: %d -> phân tích thành công: %d (lỗi: %d, cần xem lại: %d)",
            self.category_name,
            self.fetched,
            self.keyword_passed,
            self.new_by_url,
            self.level_passed,
            self.analyzed_success,
            self.analyzed_failed,
            self.needs_review,
        )


async def _process_job(
    *,
    listing: JobListingMeta,
    resume_id: int,
    resume_content: str,
    job_repo: JobRepository,
    match_repo: MatchResultRepository,
    run_repo: AgentRunRepository,
    session: AsyncSession,
    counts: _CategoryCounts,
) -> None:
    try:
        description = await fetch_detail(listing.url)
    except ItviecFetchError as exc:
        logger.warning("[fetch_jobs] fetch detail lỗi, bỏ qua job %s: %s", listing.url, exc)
        return

    if not passes_level_filter(listing.title, description):
        return
    counts.level_passed += 1

    job = await job_repo.create(
        description=description,
        title=listing.title,
        company=listing.company,
        url=listing.url,
        source=SOURCE_ITVIEC,
    )
    await session.commit()
    await session.refresh(job)

    try:
        agent = get_agent(MATCHING_AGENT)
    except (AgentUnavailableError, AnthropicConfigError) as exc:
        logger.error("[fetch_jobs] agent không khả dụng cho job %s: %s", job.id, exc)
        counts.analyzed_failed += 1
        return

    try:
        result = await agent.run(
            AgentContext(resume_text=resume_content, job_description_text=job.description, job_id=job.id)
        )
    except AgentExecutionError as exc:
        for log in exc.run_logs:
            await run_repo.log(run_log=log, job_id=job.id)
        await session.commit()
        logger.warning("[fetch_jobs] matching_agent thất bại cho job %s: %s", job.id, exc)
        counts.analyzed_failed += 1
        return

    # Ghi TẤT CẢ agent_runs trước — 1 phần tử ở chế độ 1 model, 2 phần tử ở ensemble.
    for log in result.run_logs:
        await run_repo.log(run_log=log, job_id=job.id)

    if result.needs_review:
        # Ensemble bất đồng verdict — KHÔNG lưu match_result, KHÔNG phải lỗi. Job vẫn coi như
        # xử lý xong bình thường, tiếp tục job tiếp theo.
        await session.commit()
        logger.info("[fetch_jobs] matching_agent bất đồng cho job %s — cần xem lại thủ công.", job.id)
        counts.needs_review += 1
        return

    await match_repo.create(job_id=job.id, resume_id=resume_id, output=MatchOutput.model_validate(result.output))
    await session.commit()
    counts.analyzed_success += 1


async def run_fetch_jobs() -> None:
    """Entry point cho APScheduler — fetch tất cả category, lọc, dedup, chấm điểm."""
    settings = get_settings()

    async with SessionLocal() as session:
        resume = await ResumeRepository(session).get_singleton(settings.resume_singleton_id)
        if resume is None:
            logger.warning(
                "[fetch_jobs] Chưa có resume nào được lưu — bỏ qua lần fetch này (không có gì để chấm điểm)."
            )
            return

        job_repo = JobRepository(session)
        match_repo = MatchResultRepository(session)
        run_repo = AgentRunRepository(session)

        # Dedup trong-lần-chạy: 1 job có thể xuất hiện ở nhiều category listing cùng lúc
        # (vd. vừa khớp "Data Engineer" vừa khớp "AI / Machine Learning Engineer").
        seen_this_run: set[str] = set()

        for category_name, category_url in CATEGORY_URLS.items():
            counts = _CategoryCounts(category_name)
            try:
                listings = await fetch_listing(category_url)
            except ItviecFetchError as exc:
                logger.error(
                    "[fetch_jobs] Không fetch được category '%s' (%s), bỏ qua: %s",
                    category_name,
                    category_url,
                    exc,
                )
                continue

            counts.fetched = len(listings)

            for listing in listings:
                if not matches_relevant_keyword(listing.title, listing.skill_tags):
                    continue
                counts.keyword_passed += 1

                if listing.url in seen_this_run or await job_repo.exists_by_url(listing.url):
                    continue
                seen_this_run.add(listing.url)
                counts.new_by_url += 1

                await _process_job(
                    listing=listing,
                    resume_id=resume.id,
                    resume_content=resume.content,
                    job_repo=job_repo,
                    match_repo=match_repo,
                    run_repo=run_repo,
                    session=session,
                    counts=counts,
                )

            counts.log_summary()
