"""Endpoint tạo & xem cover letter.

CHỈ tạo được cho job đã `application_status == "approved"` (xem `models/application.py`) — tín
hiệu người dùng đã thực sự muốn theo đuổi job đó, tránh tốn API call cho job có thể bị reject sau.
Luồng: Approve → (tuỳ chọn) Tạo cover letter → người dùng tự đọc/copy. KHÔNG có bước nào tự gửi
đi đâu cả — hệ thống chỉ chuẩn bị nội dung.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ErrorCode, api_error
from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.core.db import get_session
from app.integrations.anthropic import AnthropicConfigError
from app.models.match_result import MatchResult
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.cover_letter_repository import CoverLetterRepository
from app.repositories.job_repository import JobRepository
from app.repositories.match_result_repository import MatchResultRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.cover_letter import CoverLetterOutput, CoverLetterRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["cover-letters"])

COVER_LETTER_AGENT = "cover_letter_agent"


def _build_match_context(match: MatchResult | None) -> str:
    """Tóm tắt match_result mới nhất thành text ngắn cho agent tham khảo — chỉ dùng làm GỢI Ý
    nên nhấn mạnh điểm nào, agent được dặn không copy nguyên văn (xem cover_letter_v1.md)."""
    if match is None:
        return "Chưa có kết quả phân tích matching nào trước đó cho job này."
    matched = ", ".join(match.matched_requirements) or "không có mục nào nổi bật"
    return (
        f"Điểm phù hợp: {match.score}/100 ({match.verdict}). "
        f"Điểm mạnh khớp với JD: {matched}. "
        f"Nhận xét: {match.reasoning}"
    )


@router.post(
    "/{job_id}/cover-letter",
    response_model=CoverLetterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_cover_letter(
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> CoverLetterRead:
    job_repo = JobRepository(session)
    job = await job_repo.get(job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, ErrorCode.JOB_NOT_FOUND, "Job không tồn tại.")

    application_status = await ApplicationRepository(session).get_status(job_id)
    if application_status != "approved":
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.APPLICATION_NOT_APPROVED,
            "Chỉ tạo được cover letter cho job đã approve. Approve job này trước.",
        )

    settings = get_settings()
    resume = await ResumeRepository(session).get_singleton(settings.resume_singleton_id)
    if resume is None:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.RESUME_NOT_FOUND,
            "Chưa có resume nào được lưu. Lưu resume trước khi tạo cover letter.",
        )

    match = await MatchResultRepository(session).get_latest_for_job(job_id)
    match_context = _build_match_context(match)

    try:
        agent = get_agent(COVER_LETTER_AGENT)
    except AgentUnavailableError as exc:
        logger.error("Agent không khả dụng: %s", exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.AGENT_UNAVAILABLE,
            "Chức năng tạo cover letter hiện không khả dụng.",
            job_id=job.id,
        ) from exc
    except AnthropicConfigError as exc:
        logger.error("Cấu hình Anthropic sai: %s", exc)
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.AGENT_MISCONFIGURED,
            "Chưa cấu hình khoá API cho dịch vụ tạo cover letter.",
            job_id=job.id,
        ) from exc

    run_repo = AgentRunRepository(session)

    try:
        result = await agent.run(
            AgentContext(
                resume_text=resume.content,
                job_description_text=job.description,
                job_id=job.id,
                metadata={"match_context": match_context},
            )
        )
    except AgentExecutionError as exc:
        for log in exc.run_logs:
            await run_repo.log(run_log=log, job_id=job.id)
        await session.commit()
        logger.warning("cover_letter_agent thất bại cho job %s: %s", job.id, exc)
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AGENT_FAILED,
            "Không tạo được cover letter cho job này. Bạn có thể thử lại.",
            job_id=job.id,
        ) from exc

    for log in result.run_logs:
        await run_repo.log(run_log=log, job_id=job.id)

    output = CoverLetterOutput.model_validate(result.output)
    cover_letter = await CoverLetterRepository(session).create(
        job_id=job.id,
        resume_id=resume.id,
        content=output.cover_letter_text,
    )
    await session.commit()
    await session.refresh(cover_letter)

    return CoverLetterRead.model_validate(cover_letter)


@router.get("/{job_id}/cover-letter", response_model=CoverLetterRead)
async def get_cover_letter(
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> CoverLetterRead:
    """Trả bản mới nhất — 404 nếu job không tồn tại HOẶC job tồn tại nhưng chưa từng tạo cover
    letter nào (2 tình huống 404 khác nhau, phân biệt qua `code`)."""
    job = await JobRepository(session).get(job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, ErrorCode.JOB_NOT_FOUND, "Job không tồn tại.")

    cover_letter = await CoverLetterRepository(session).get_latest_for_job(job_id)
    if cover_letter is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.COVER_LETTER_NOT_FOUND,
            "Chưa có cover letter nào cho job này.",
        )
    return CoverLetterRead.model_validate(cover_letter)
