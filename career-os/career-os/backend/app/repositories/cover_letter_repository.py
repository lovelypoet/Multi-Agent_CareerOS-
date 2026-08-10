"""Truy vấn bảng `cover_letters` — append-only, giống `MatchResultRepository`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cover_letter import CoverLetter


class CoverLetterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, job_id: int, resume_id: int, content: str) -> CoverLetter:
        cover_letter = CoverLetter(job_id=job_id, resume_id=resume_id, content=content)
        self.session.add(cover_letter)
        await self.session.flush()
        return cover_letter

    async def get_latest_for_job(self, job_id: int) -> CoverLetter | None:
        """Bản mới nhất của job — có thể có nhiều row/job (người dùng tạo lại nhiều lần), tie-break
        bằng `id` để kết quả luôn xác định, giống cách `JobRepository` xử lý cho `match_results`."""
        stmt = (
            select(CoverLetter)
            .where(CoverLetter.job_id == job_id)
            .order_by(CoverLetter.created_at.desc(), CoverLetter.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)
