"""Endpoint approve/reject job — thiết kế lazy (xem `models/application.py`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ErrorCode, api_error
from app.core.db import get_session
from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.schemas.application import ApplicationRead, ApplicationUpdateRequest

router = APIRouter(prefix="/api/jobs", tags=["applications"])


@router.patch("/{job_id}/application", response_model=ApplicationRead)
async def update_application_status(
    job_id: int,
    payload: ApplicationUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> ApplicationRead:
    """Upsert theo `job_id`: bấm Approve rồi Reject sau đó thì status chuyển thẳng, không tạo
    row thứ 2 — không cần validate thứ tự chuyển trạng thái.

    Query job tồn tại TRƯỚC khi upsert, thay vì bắt IntegrityError của FK constraint — CHECK
    constraint (status sai) và FK constraint (job_id sai) đều ném cùng `IntegrityError`, dễ
    nhầm lẫn 2 nguyên nhân nếu chỉ bắt exception chung chung.
    """
    job = await JobRepository(session).get(job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, ErrorCode.JOB_NOT_FOUND, "Job không tồn tại.")

    application = await ApplicationRepository(session).upsert(job_id=job_id, status=payload.status)
    await session.commit()
    await session.refresh(application)
    return ApplicationRead.model_validate(application)
