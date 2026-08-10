"""Endpoint xem danh sách email đã phân loại liên quan tới ứng tuyển (Phase 3 việc #1, giai
đoạn 1 — chỉ đọc & phân loại, KHÔNG có hành động nào khác)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.repositories.email_notification_repository import EmailNotificationRepository
from app.schemas.email_notification import EmailNotificationRead, EmailNotificationWithJob
from app.schemas.job import JobRead

router = APIRouter(prefix="/api/email-notifications", tags=["email-notifications"])


@router.get("", response_model=list[EmailNotificationWithJob])
async def list_email_notifications(
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[EmailNotificationWithJob]:
    """Danh sách email đã phân loại LIÊN QUAN, mới nhất lên đầu.

    BẮT BUỘC lọc `is_relevant = true` ở đây (`EmailNotificationRepository.list_relevant` đã tự
    lọc) — bảng `email_notifications` chứa CẢ email không liên quan để phục vụ dedup (xem
    docstring model), tầng API này là nơi duy nhất chặn không cho email "không liên quan" lộ ra
    UI.
    """
    limit = max(1, min(limit, 200))
    rows = await EmailNotificationRepository(session).list_relevant(limit=limit)
    return [
        EmailNotificationWithJob(
            notification=EmailNotificationRead.model_validate(notification),
            job=JobRead.model_validate(job) if job is not None else None,
        )
        for notification, job in rows
    ]
