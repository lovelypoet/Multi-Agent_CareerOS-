"""Truy vấn bảng `match_results`."""

from __future__ import annotations

from app.models.match_result import MatchResult
from app.schemas.match import MatchOutput
from sqlalchemy.ext.asyncio import AsyncSession


class MatchResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
