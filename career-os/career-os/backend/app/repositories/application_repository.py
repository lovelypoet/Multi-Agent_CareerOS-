"""Truy vấn bảng `applications` — CRUD của riêng bảng này, không đụng tới `jobs`/`match_results`."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_status(self, job_id: int) -> str:
        """Thiết kế lazy (xem `models/application.py`): không có row nghĩa là 'pending'."""
        stmt = select(Application.status).where(Application.job_id == job_id)
        status = await self.session.scalar(stmt)
        return status or "pending"

    async def upsert(self, *, job_id: int, status: str) -> Application:
        """Upsert theo `job_id` — chưa có row thì tạo, đã có thì update status.

        BUG ĐÃ VERIFY: `onupdate=func.now()` khai trong model KHÔNG tự chạy qua đường
        `ON CONFLICT DO UPDATE` — phải liệt kê tường minh `updated_at: func.now()` trong
        `set_` dưới đây, nếu không `updated_at` sẽ đứng yên mãi mãi sau lần ghi đầu tiên.
        """
        stmt = (
            pg_insert(Application)
            .values(job_id=job_id, status=status)
            .on_conflict_do_update(
                index_elements=[Application.job_id],
                set_={"status": status, "updated_at": func.now()},
            )
            .returning(Application)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
