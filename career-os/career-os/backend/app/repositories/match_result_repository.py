"""Truy vấn bảng `match_results`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match_result import MatchResult
from app.models.resume import Resume
from app.schemas.match import MatchOutput


class MatchResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_for_job(
        self, job_id: int, *, resume_id: int | None = None
    ) -> MatchResult | None:
        """Dùng để build `match_context` cho `cover_letter_agent` — job có thể có nhiều lần phân
        tích lại, tie-break bằng `id` để kết quả luôn xác định."""
        stmt = select(MatchResult).where(MatchResult.job_id == job_id)
        if resume_id is not None:
            stmt = stmt.where(MatchResult.resume_id == resume_id)
        stmt = stmt.order_by(MatchResult.created_at.desc(), MatchResult.id.desc()).limit(1)
        return await self.session.scalar(stmt)

    async def create(self, *, job_id: int, resume_id: int, output: MatchOutput) -> MatchResult:
        """Chỉ được gọi khi output ĐÃ validate — không bao giờ lưu dữ liệu rác vào bảng này."""
        resume = await self.session.get(Resume, resume_id)
        if resume is None:
            raise RuntimeError(f"Resume version {resume_id} does not exist.")
        match = MatchResult(
            job_id=job_id,
            resume_id=resume_id,
            resume=resume,
            score=output.score,
            verdict=output.verdict,
            reasoning=output.reasoning,
            matched_requirements=output.matched_requirements,
            missing_requirements=output.missing_requirements,
            suggestions=output.suggestions,
            jd_analysis=output.jd_analysis.model_dump() if output.jd_analysis is not None else None,
            requirement_assessments=[
                assessment.model_dump() for assessment in output.requirement_assessments
            ]
            if output.jd_analysis is not None
            else None,
            analysis_basis="evidence_based" if output.jd_analysis is not None else "legacy",
        )
        self.session.add(match)
        await self.session.flush()
        return match
