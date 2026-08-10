"""Truy vấn bảng `match_results`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match_result import MatchResult
from app.schemas.match import MatchOutput


class MatchResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_for_job(self, job_id: int) -> MatchResult | None:
        """Dùng để build `match_context` cho `cover_letter_agent` — job có thể có nhiều lần phân
        tích lại, tie-break bằng `id` để kết quả luôn xác định."""
        stmt = (
            select(MatchResult)
            .where(MatchResult.job_id == job_id)
            .order_by(MatchResult.created_at.desc(), MatchResult.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def create(self, *, job_id: int, resume_id: int, output: MatchOutput) -> MatchResult:
        """Chỉ được gọi khi output ĐÃ validate — không bao giờ lưu dữ liệu rác vào bảng này."""
        match = MatchResult(
            job_id=job_id,
            resume_id=resume_id,
            score=output.score,
            verdict=output.verdict,
            reasoning=output.reasoning,
            matched_requirements=output.matched_requirements,
            missing_requirements=output.missing_requirements,
            suggestions=output.suggestions,
        )
        self.session.add(match)
        await self.session.flush()
        return match
