"""Endpoint lưu / đọc resume. Phase 0: đúng 1 resume, luôn ở id cố định."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ErrorCode, api_error
from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.core.db import get_session
from app.integrations.anthropic import AnthropicConfigError
from app.integrations.embedding_client import EmbeddingCallError, embed_text
from app.integrations.pdf_extractor import (
    PdfEmptyTextError,
    PdfEncryptedError,
    PdfExtractionError,
    extract_text_from_pdf,
)
from app.models.resume import Resume
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.cv_extraction_repository import CVExtractionRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.cv_extraction import CVExtractedKeywordsRead, CVExtractionOutput
from app.schemas.resume import ResumeRead, ResumeUpsertRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_PDF_BYTES = 5 * 1024 * 1024
CV_EXTRACTION_AGENT = "cv_extraction_agent"


async def _run_cv_extraction(*, resume: Resume, session: AsyncSession) -> None:
    """Chạy `cv_extraction_agent` ĐỒNG BỘ ngay sau khi lưu resume — lỗi ở đây TUYỆT ĐỐI KHÔNG
    được raise ra ngoài, KHÔNG được làm hỏng response lưu resume đã thành công (đúng nguyên tắc
    "lưu trước, phân tích sau, lỗi phân tích không mất dữ liệu gốc" xuyên suốt từ Phase 0). Nếu
    lỗi, `cv_extracted_keywords` cũ (nếu có) được GIỮ NGUYÊN — không xoá chỉ vì lần này thất bại.

    Phase 3 việc #4 mục 3 — sau khi trích xuất xong, NẾU có ít nhất 1 trong 2 `domains`/
    `key_skills` không rỗng thì tính embedding từ CHÍNH kết quả agent vừa chạy (không query lại
    DB) và lưu vào `resumes.embedding`. Nếu agent lỗi, HOẶC trích xuất thành công nhưng cả 2
    đều rỗng (case hợp lệ, không phải lỗi), KHÔNG gọi `embed_text()` — giữ nguyên embedding cũ
    (nếu có), không embed chuỗi rỗng (không mang tín hiệu gì, chỉ gây nhiễu khi lọc/tìm kiếm).
    Lỗi ở bước embedding KHÔNG được làm hỏng việc đã lưu resume/CV extraction thành công.
    """
    run_repo = AgentRunRepository(session)

    try:
        agent = get_agent(CV_EXTRACTION_AGENT)
    except (AgentUnavailableError, AnthropicConfigError) as exc:
        logger.error("cv_extraction_agent không khả dụng: %s", exc)
        return

    try:
        result = await agent.run(AgentContext(resume_text=resume.content, job_description_text=""))
    except AgentExecutionError as exc:
        for log in exc.run_logs:
            await run_repo.log(run_log=log, job_id=None)
        await session.commit()
        logger.warning("cv_extraction_agent thất bại cho resume %s: %s", resume.id, exc)
        return

    for log in result.run_logs:
        await run_repo.log(run_log=log, job_id=None)

    output = CVExtractionOutput.model_validate(result.output)
    await CVExtractionRepository(session).upsert(resume_id=resume.id, output=output)
    await session.commit()

    if not output.domains and not output.key_skills:
        return

    combined_text = ", ".join([*output.domains, *output.key_skills])
    try:
        embedding = await embed_text(combined_text)
    except EmbeddingCallError as exc:
        logger.warning("Không tạo được embedding cho resume %s: %s", resume.id, exc)
        return

    await ResumeRepository(session).set_embedding(resume_id=resume.id, embedding=embedding)
    await session.commit()


@router.post("", response_model=ResumeRead)
async def save_resume(
    payload: ResumeUpsertRequest,
    session: AsyncSession = Depends(get_session),
) -> ResumeRead:
    """UPDATE row resume duy nhất (upsert theo id cố định), không bao giờ INSERT row mới."""
    settings = get_settings()
    resume = await ResumeRepository(session).upsert_singleton(
        resume_id=settings.resume_singleton_id,
        content=payload.content,
    )
    await session.commit()

    # Tự động rút từ khóa ngay sau khi lưu — không cần nút riêng, không tách job nền (xem
    # docstring `_run_cv_extraction`). Response lưu resume KHÔNG phụ thuộc kết quả bước này.
    await _run_cv_extraction(resume=resume, session=session)

    return ResumeRead.model_validate(resume)


@router.get("", response_model=ResumeRead)
async def read_resume(session: AsyncSession = Depends(get_session)) -> ResumeRead:
    """FE dùng để đổ nội dung cũ vào textarea khi mở trang resume."""
    settings = get_settings()
    resume = await ResumeRepository(session).get_singleton(settings.resume_singleton_id)
    if resume is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.RESUME_NOT_FOUND,
            "Chưa có resume nào được lưu.",
        )
    return ResumeRead.model_validate(resume)


@router.post("/upload", response_model=ResumeRead)
async def upload_resume_pdf(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ResumeRead:
    """Upload CV dạng PDF — trích text rồi lưu qua đúng `upsert_singleton` đã có từ Phase 0.

    Endpoint MỚI, không sửa `POST /api/resume` hiện có — 2 cách lưu resume (dán text / upload
    PDF) độc lập, cùng đổ vào 1 row resume duy nhất.
    """
    # 1) Check size TRƯỚC khi đọc gì — tránh tốn CPU parse PDF rác. `file.size` đã có sẵn
    # ngay khi vào handler (Starlette tự tính lúc parse multipart).
    if file.size is not None and file.size > MAX_PDF_BYTES:
        raise api_error(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            ErrorCode.PDF_TOO_LARGE,
            "File vượt quá 5MB.",
        )

    # 2) Đọc file ĐÚNG 1 LẦN. UploadFile là stream có trạng thái — đọc thêm lần 2 sẽ mất
    # phần đầu đã đọc trước đó (đã tự tay verify: mất đúng 4 byte header %PDF).
    content = await file.read()

    # 3) Magic bytes trên chính `content` vừa đọc — không tin Content-Type header hay đuôi
    # file, cả hai đều có thể sai/giả.
    if content[:4] != b"%PDF":
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.PDF_NOT_A_PDF,
            "File tải lên không phải PDF hợp lệ.",
        )

    try:
        text = extract_text_from_pdf(content)
    except PdfEncryptedError as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, ErrorCode.PDF_ENCRYPTED, str(exc)) from exc
    except PdfEmptyTextError as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, ErrorCode.PDF_EMPTY_TEXT, str(exc)) from exc
    except PdfExtractionError as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, ErrorCode.PDF_PARSE_FAILED, str(exc)) from exc

    settings = get_settings()
    resume = await ResumeRepository(session).upsert_singleton(
        resume_id=settings.resume_singleton_id,
        content=text,
    )
    await session.commit()

    await _run_cv_extraction(resume=resume, session=session)

    return ResumeRead.model_validate(resume)


@router.get("/extracted-keywords", response_model=CVExtractedKeywordsRead)
async def read_extracted_keywords(session: AsyncSession = Depends(get_session)) -> CVExtractedKeywordsRead:
    """Minh bạch cho người dùng thấy hệ thống tự rút ra gì từ CV để bổ sung bộ lọc job (Phase 1)
    — xem `workers/fetch_jobs.py`. 404 nếu chưa có (chưa từng lưu resume, hoặc lần trích xuất đầu
    tiên chưa chạy xong/lỗi)."""
    settings = get_settings()
    extracted = await CVExtractionRepository(session).get_singleton(settings.resume_singleton_id)
    if extracted is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.CV_KEYWORDS_NOT_FOUND,
            "Chưa có từ khóa nào được trích xuất từ CV.",
        )
    return CVExtractedKeywordsRead.model_validate(extracted)
