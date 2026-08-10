"""Endpoint cho job: phân tích 1 job description và xem lại lịch sử."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ErrorCode, api_error
from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.core.db import get_session
from app.integrations.anthropic import AnthropicConfigError
from app.integrations.embedding_client import EmbeddingCallError, embed_text
from app.models.job import Job
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.match_result_repository import MatchResultRepository
from app.repositories.resume_repository import ResumeRepository
from app.repositories.scam_assessment_repository import ScamAssessmentRepository
from app.schemas.agent_run import AgentRunRead
from app.schemas.job import JobAnalyzeRequest, JobAnalyzeResponse, JobRead, JobWithMatch
from app.schemas.match import MatchOutput, MatchResultRead
from app.schemas.scam_detection import ScamAssessmentRead, ScamDetectionOutput

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])

MATCHING_AGENT = "matching_agent"
SCAM_DETECTION_AGENT = "scam_detection_agent"


async def _run_scam_detection(*, job: Job, session: AsyncSession) -> None:
    """Chạy `scam_detection_agent` ĐỘC LẬP với `matching_agent` — KHÔNG raise ra ngoài, KHÔNG
    được cản luồng phân tích matching dù thành công, thất bại, hay bất đồng (xem Phase 3 việc #3
    mục 5: 1 agent lỗi không được cản agent còn lại, cả 2 kết quả hiển thị cùng lúc cho người
    dùng tự cân nhắc, không tự động chặn/ẩn job nào).
    """
    run_repo = AgentRunRepository(session)

    try:
        agent = get_agent(SCAM_DETECTION_AGENT)
    except (AgentUnavailableError, AnthropicConfigError) as exc:
        logger.error("scam_detection_agent không khả dụng cho job %s: %s", job.id, exc)
        return

    try:
        # resume_text="" — scam detection chỉ đánh giá bản thân JD, không liên quan CV
        # (AgentContext là contract dùng chung cho mọi agent, field này không có ý nghĩa ở đây).
        result = await agent.run(AgentContext(resume_text="", job_description_text=job.description, job_id=job.id))
    except AgentExecutionError as exc:
        for log in exc.run_logs:
            await run_repo.log(run_log=log, job_id=job.id)
        await session.commit()
        logger.warning("scam_detection_agent thất bại cho job %s: %s", job.id, exc)
        return

    for log in result.run_logs:
        await run_repo.log(run_log=log, job_id=job.id)

    if result.needs_review:
        await session.commit()
        logger.info("scam_detection_agent bất đồng cho job %s — cần xem lại thủ công.", job.id)
        return

    await ScamAssessmentRepository(session).upsert(
        job_id=job.id, output=ScamDetectionOutput.model_validate(result.output)
    )
    await session.commit()


@router.post("/analyze", response_model=JobAnalyzeResponse, status_code=status.HTTP_201_CREATED)
async def analyze_job(
    payload: JobAnalyzeRequest,
    session: AsyncSession = Depends(get_session),
) -> JobAnalyzeResponse:
    """Lưu job → chạy matching agent → lưu kết quả → trả về.

    Thứ tự này là cố ý: job được lưu và COMMIT trước khi gọi AI. Nếu gọi AI xong mới lưu thì lần
    nào AI lỗi là mất luôn job vừa dán, trong khi mục tiêu Phase 0 là giữ được lịch sử.
    """
    settings = get_settings()
    resume_repo = ResumeRepository(session)
    job_repo = JobRepository(session)

    resume = await resume_repo.get_singleton(settings.resume_singleton_id)
    if resume is None:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.RESUME_NOT_FOUND,
            "Chưa có resume nào được lưu. Lưu resume trước khi phân tích job.",
        )

    # 1) Lưu job trước, commit ngay để không mất dữ liệu nếu bước sau lỗi.
    job = await job_repo.create(description=payload.description)
    await session.commit()
    await session.refresh(job)

    # 1.5) scam_detection_agent chạy ĐỘC LẬP với matching — không chặn, không phụ thuộc kết quả
    # của nhau. Gọi tuần tự (không cần asyncio.gather) — quy mô cá nhân, gọi tuần tự đơn giản là
    # đủ, không cần thêm độ phức tạp xử lý lỗi cho việc chạy đồng thời khi không thực sự cần tốc độ.
    await _run_scam_detection(job=job, session=session)

    # 2) Lấy agent qua registry (public code không import module private trực tiếp).
    try:
        agent = get_agent(MATCHING_AGENT)
    except AgentUnavailableError as exc:
        logger.error("Agent không khả dụng: %s", exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.AGENT_UNAVAILABLE,
            "Chức năng phân tích hiện không khả dụng.",
            job_id=job.id,
        ) from exc
    except AnthropicConfigError as exc:
        logger.error("Cấu hình Anthropic sai: %s", exc)
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.AGENT_MISCONFIGURED,
            "Chưa cấu hình khoá API cho dịch vụ phân tích.",
            job_id=job.id,
        ) from exc

    run_repo = AgentRunRepository(session)

    # 3) Chạy agent. Thành công hay thất bại đều phải ghi 1 row vào `agent_runs`.
    try:
        result = await agent.run(
            AgentContext(
                resume_text=resume.content,
                job_description_text=job.description,
                job_id=job.id,
            )
        )
    except AgentExecutionError as exc:
        for log in exc.run_logs:
            await run_repo.log(run_log=log, job_id=job.id)
        await session.commit()
        logger.warning("matching_agent thất bại cho job %s: %s", job.id, exc)
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AGENT_FAILED,
            "Không phân tích được job này. Job đã được lưu, bạn có thể thử lại.",
            job_id=job.id,
        ) from exc

    # 4) Ghi TẤT CẢ agent_runs trước — 1 phần tử ở chế độ 1 model, 2 phần tử ở ensemble. Cùng 1
    # đoạn code xử lý được cả 2 trường hợp, không cần nhánh điều kiện riêng.
    for log in result.run_logs:
        await run_repo.log(run_log=log, job_id=job.id)

    # 5) Ensemble bất đồng verdict: KHÔNG có output đủ tin cậy để lưu match_result — đây KHÔNG
    # phải lỗi (cả 2 model đều chạy đúng), chỉ dừng ở việc đã ghi agent_runs, trả về không có
    # match. FE sẽ thấy job này qua lịch sử với analysis_status='needs_review'.
    if result.needs_review:
        await session.commit()
        logger.info("matching_agent bất đồng cho job %s — cần xem lại thủ công.", job.id)
        return JobAnalyzeResponse(job=JobRead.model_validate(job), match=None)

    # 6) Đồng thuận (hoặc provider đơn): lưu kết quả như bình thường, cùng 1 transaction.
    match_repo = MatchResultRepository(session)
    match = await match_repo.create(
        job_id=job.id,
        resume_id=resume.id,
        output=MatchOutput.model_validate(result.output),
    )
    await session.commit()
    await session.refresh(match)

    return JobAnalyzeResponse(
        job=JobRead.model_validate(job),
        match=MatchResultRead.model_validate(match),
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
