"""Query tổng hợp cho dashboard — đụng cả 3 bảng `jobs`, `match_results`, `applications`,
nên KHÔNG thuộc về repository nào ở trên (mỗi repository chỉ lo đúng 1 bảng)."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.application import Application
from app.models.job import Job
from app.models.match_result import MatchResult
from app.schemas.dashboard import DashboardSummary


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(self, *, timezone: str) -> DashboardSummary:
        return DashboardSummary(
            jobs_today=await self._jobs_today(timezone),
            approved_count=await self._approved_count(),
            avg_score=await self._avg_score(),
        )

    async def _jobs_today(self, timezone: str) -> int:
        """"Hôm nay" theo giờ VN, KHÔNG theo UTC của server — lệch múi giờ sẽ tính sai job
        phân tích lúc rạng sáng giờ VN."""
        stmt = text(
            "SELECT COUNT(*) FROM jobs "
            "WHERE (created_at AT TIME ZONE :tz)::date = (now() AT TIME ZONE :tz)::date"
        )
        result = await self.session.execute(stmt, {"tz": timezone})
        return result.scalar_one()

    async def _approved_count(self) -> int:
        """Tổng lũy kế từ trước tới giờ — KHÔNG lọc theo ngày (đã chốt)."""
        stmt = select(func.count()).select_from(Application).where(Application.status == "approved")
        return await self.session.scalar(stmt)

    async def _avg_score(self) -> float | None:
        """Trung bình score của match_result MỚI NHẤT mỗi job (không phải toàn bảng
        match_results) — dùng lại đúng kỹ thuật ROW_NUMBER() của
        `JobRepository.list_with_latest_match_and_status`, tránh đếm trùng job có phân
        tích lại nhiều lần.
        """
        ranked = select(
            MatchResult,
            func.row_number()
            .over(
                partition_by=MatchResult.job_id,
                order_by=(MatchResult.created_at.desc(), MatchResult.id.desc()),
            )
            .label("rn"),
        ).subquery()

        latest = select(ranked).where(ranked.c.rn == 1).subquery()
        LatestMatch = aliased(MatchResult, latest)

        stmt = select(func.avg(LatestMatch.score))
        avg = await self.session.scalar(stmt)
        return float(avg) if avg is not None else None
