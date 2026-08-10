"""Truy vấn bảng `email_notifications`. Bảng LƯU MỌI email đã xử lý (kể cả `is_relevant=false`,
xem docstring `models/email_notification.py`) — repository này KHÔNG tự lọc `is_relevant`, tầng
API (`api/email_notifications.py`) chịu trách nhiệm lọc trước khi trả cho FE."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_notification import EmailNotification
from app.models.job import Job


class EmailNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_for_account(self, *, account_email: str, gmail_message_id: str) -> bool:
        """Check dedup TRƯỚC TIÊN cho 1 email — bất kể `is_relevant` giá trị gì (xem lý do ở
        docstring model)."""
        stmt = select(
            exists().where(
                EmailNotification.account_email == account_email,
                EmailNotification.gmail_message_id == gmail_message_id,
            )
        )
        return bool(await self.session.scalar(stmt))

    async def get_latest_received_at(self, account_email: str) -> datetime | None:
        """Mốc thời gian quét gần nhất CỦA RIÊNG tài khoản này — NULL nghĩa là tài khoản chưa
        từng được quét lần nào (worker dùng khoảng lùi cố định cho trường hợp này, xem
        `workers/fetch_emails.py`)."""
        stmt = select(func.max(EmailNotification.received_at)).where(
            EmailNotification.account_email == account_email
        )
        return await self.session.scalar(stmt)

    async def create(
        self,
        *,
        account_email: str,
        gmail_message_id: str,
        is_relevant: bool,
        job_id: int | None,
        category: str | None,
        company_name_mentioned: str | None,
        summary: str,
        sender: str,
        subject: str,
        received_at: datetime,
    ) -> EmailNotification:
        """LUÔN lưu, bất kể `is_relevant` — đây chính là bản ghi dedup cho lần quét sau."""
        notification = EmailNotification(
            account_email=account_email,
            gmail_message_id=gmail_message_id,
            is_relevant=is_relevant,
            job_id=job_id,
            category=category,
            company_name_mentioned=company_name_mentioned,
            summary=summary,
            sender=sender,
            subject=subject,
            received_at=received_at,
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_relevant(self, *, limit: int = 100) -> list[tuple[EmailNotification, Job | None]]:
        """CHỈ email `is_relevant=true`, mới nhất lên đầu, kèm `Job` liên quan nếu `job_id` khớp
        được — dùng cho `GET /api/email-notifications`. OUTER JOIN (không phải INNER) vì
        `job_id` có thể `NULL` (không khớp job nào, hoặc khớp nhiều hơn 1 job — xem mục 4)."""
        stmt = (
            select(EmailNotification, Job)
            .outerjoin(Job, Job.id == EmailNotification.job_id)
            .where(EmailNotification.is_relevant.is_(True))
            .order_by(EmailNotification.received_at.desc(), EmailNotification.id.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]
