"""Endpoint cho job: phân tích 1 job description và xem lại lịch sử."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ErrorCode, api_error
from app.core.db import get_session
from app.integrations.embedding_client import EmbeddingCallError, embed_text
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.job_repository import JobRepository
from app.schemas.agent_run import AgentRunRead
from app.schemas.job import JobAnalyzeRequest, JobAnalyzeResponse, JobRead, JobWithMatch
from app.schemas.match import MatchResultRead
from app.schemas.scam_detection import ScamAssessmentRead
from app.services.matching import (
    MatchingAgentMisconfiguredError,
    MatchingAgentUnavailableError,
    MatchingExecutionError,
    MatchingService,
    ResumeRequiredError,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.post("/analyze", response_model=JobAnalyzeResponse, status_code=status.HTTP_201_CREATED)
async def analyze_job(
    payload: JobAnalyzeRequest,
    session: AsyncSession = Depends(get_session),
) -> JobAnalyzeResponse:
    try:
        outcome = await MatchingService(session).match_job(payload.description)
    except ResumeRequiredError as exc:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.RESUME_NOT_FOUND,
            "Chưa có resume nào được lưu. Lưu resume trước khi phân tích job.",
        ) from exc
    except MatchingAgentUnavailableError as exc:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.AGENT_UNAVAILABLE,
            "Chức năng phân tích hiện không khả dụng.",
            job_id=exc.job_id,
        ) from exc
    except MatchingAgentMisconfiguredError as exc:
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.AGENT_MISCONFIGURED,
            "Chưa cấu hình khoá API cho dịch vụ phân tích.",
            job_id=exc.job_id,
        ) from exc
    except MatchingExecutionError as exc:
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AGENT_FAILED,
            "Không phân tích được job này. Job đã được lưu, bạn có thể thử lại.",
            job_id=exc.job_id,
        ) from exc

    return JobAnalyzeResponse(
        job=JobRead.model_validate(outcome.job),
        match=MatchResultRead.model_validate(outcome.match) if outcome.match is not None else None,
    )


@router.get("", response_model=list[JobWithMatch])
async def list_jobs(
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[JobWithMatch]:
    """Lịch sử các job đã phân tích, kèm match_result mới nhất + trạng thái approve/reject +
    trạng thái phân tích matching + kết quả/trạng thái scam detection — 2 agent độc lập, 2 trạng
    thái độc lập (`analysis_status`/`scam_check_status`), không gộp chung."""
    limit = max(1, min(limit, 200))
    rows = await JobRepository(session).list_with_latest_match_and_status(limit=limit)
    return [
        JobWithMatch(
            job=JobRead.model_validate(job),
            match=MatchResultRead.model_validate(match) if match is not None else None,
            application_status=application_status,
            analysis_status=analysis_status,
            scam=ScamAssessmentRead.model_validate(scam) if scam is not None else None,
            scam_check_status=scam_check_status,
        )
        for job, match, application_status, analysis_status, scam, scam_check_status in rows
    ]


@router.get("/search", response_model=list[JobRead])
async def search_jobs(
    q: str = Query(min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[JobRead]:
    """Tìm kiếm job theo ý nghĩa (Phase 3 việc #4 mục 5) — `q` là câu tự nhiên (vd "công việc
    liên quan tới machine learning cho fresher"), KHÔNG phải từ khóa chính xác. Chỉ trả job đã
    có `embedding` (xem `JobRepository.search_by_embedding`) — job cũ trước tính năng này không
    xuất hiện, chấp nhận được, không backfill bắt buộc.
    """
    try:
        query_embedding = await embed_text(q)
    except EmbeddingCallError as exc:
        logger.error("Không tạo được embedding cho câu tìm kiếm '%s': %s", q, exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.SEARCH_UNAVAILABLE,
            "Chức năng tìm kiếm hiện không khả dụng.",
        ) from exc

    jobs = await JobRepository(session).search_by_embedding(query_embedding=query_embedding)
    return [JobRead.model_validate(job) for job in jobs]


@router.get("/{job_id}/agent-runs", response_model=list[AgentRunRead])
async def get_job_agent_runs(
    job_id: int,
    agent_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[AgentRunRead]:
    """Lịch sử thô các lần gọi agent cho 1 job — dùng để xem 2 model (ensemble) nói gì khi bất
    đồng, nhưng không giới hạn chỉ dùng cho trường hợp đó, hữu ích debug bất kỳ job nào.

    `agent_name` (tuỳ chọn, vd. `scam_detection_agent`) lọc chỉ lấy row của đúng agent đó — cần
    thiết từ khi có >1 agent cùng ghi vào `agent_runs` và cùng khả năng rơi vào `needs_review`
    (matching, scam): không lọc thì 1 job vừa bất đồng ở scam vừa có agent_runs của matching sẽ
    trả lẫn cả 2 loại, sai ngữ cảnh khi FE chỉ muốn hiện chi tiết bất đồng của 1 agent. KHÔNG
    truyền `agent_name` thì trả TOÀN BỘ như hành vi cũ (tương thích ngược).

    404 nếu job không tồn tại — nếu job tồn tại nhưng chưa từng chạy agent (hoặc chưa từng chạy
    đúng `agent_name` được lọc), trả về mảng rỗng (không phải lỗi, chỉ là chưa có lịch sử).
    """
    job = await JobRepository(session).get(job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, ErrorCode.JOB_NOT_FOUND, "Job không tồn tại.")

    runs = await AgentRunRepository(session).list_for_job(job_id, agent_name=agent_name)
    return [AgentRunRead.model_validate(run) for run in runs]
