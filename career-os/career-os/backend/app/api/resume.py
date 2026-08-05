"""Endpoint lưu / đọc resume. Phase 0: đúng 1 resume, luôn ở id cố định."""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ErrorCode, api_error
from app.core.config import get_settings
from app.core.db import get_session
from app.integrations.pdf_extractor import (
    PdfEmptyTextError,
    PdfEncryptedError,
    PdfExtractionError,
    extract_text_from_pdf,
)
from app.repositories.resume_repository import ResumeRepository
from app.schemas.resume import ResumeRead, ResumeUpsertRequest

router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_PDF_BYTES = 5 * 1024 * 1024


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
    return ResumeRead.model_validate(resume)
