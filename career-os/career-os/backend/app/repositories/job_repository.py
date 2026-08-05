"""Truy vấn bảng `jobs`."""

from __future__ import annotations

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.job import Job
from app.models.match_result import MatchResult


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        description: str,
        title: str | None = None,
        company: str | None = None,
        url: str | None = None,
        source: str = "manual",
    ) -> Job:
        """Tạo row job mới.

        Phase 0 (dán tay): chỉ truyền `description`, title/company/url để NULL, source mặc
        định 'manual'. Phase 1 (fetch tự động): `fetch_jobs.py` truyền đủ title/company/url,
        source='itviec'.
        """
        job = Job(description=description, title=title, company=company, url=url, source=source)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: int) -> Job | None:
        return await self.session.get(Job, job_id)

    async def exists_by_url(self, url: str) -> bool:
        """Dùng để dedup trước khi fetch detail — job đã có url này thì bỏ qua, không fetch
        lại detail, không gọi lại matching_agent (xem prompt Phase 1 mục 3).
        """
        stmt = select(exists().where(Job.url == url))
        return bool(await self.session.scalar(stmt))

    async def list_with_latest_match_and_status(
        self, *, limit: int = 100
    ) -> list[tuple[Job, MatchResult | None, str, str]]:
        """Danh sách job kèm match_result MỚI NHẤT + trạng thái approve/reject + trạng thái
        phân tích, mới nhất lên đầu.

        Dùng ROW_NUMBER() thay vì `JOIN ... MAX(created_at)`: nếu 2 lần phân tích cùng 1 job rơi
        vào cùng một mốc thời gian thì cách kia trả ra 2 dòng cho 1 job. Tie-break thêm bằng `id`
        để kết quả luôn xác định.

        OUTER JOIN chứ không phải INNER cho cả match lẫn application: job đã lưu nhưng agent
        lỗi thì vẫn phải hiện trong lịch sử (đúng tinh thần "lưu job trước, phân tích sau"); job
        chưa từng approve/reject (thiết kế lazy, không có row applications) vẫn phải hiện với
        status 'pending' qua COALESCE, không bị rớt khỏi kết quả.

        `analysis_status` suy ra từ dữ liệu, KHÔNG lưu cột riêng (giống cách `application_status`
        đã làm) — thứ tự ưu tiên CỐ Ý theo đúng thứ tự này, không đổi:
          1. Có match_result -> 'analyzed'
          2. Không có match_result, có >=1 agent_runs.error IS NOT NULL -> 'failed'
          3. Không có match_result, >=2 agent_runs thành công (error IS NULL) với verdict khác
             nhau (đếm qua DISTINCT, không đếm số row — job có nhiều hơn 2 agent_runs theo thời
             gian, ví dụ phân tích lại, vẫn đúng) -> 'needs_review'
          4. Còn lại -> 'pending' (chưa từng chạy agent lần nào)
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

        has_failed_run = exists().where(AgentRun.job_id == Job.id, AgentRun.error.is_not(None))

        distinct_verdict_count = (
            select(func.count(func.distinct(AgentRun.output["verdict"].astext)))
            .where(AgentRun.job_id == Job.id, AgentRun.error.is_(None))
            .correlate(Job)
            .scalar_subquery()
        )

        analysis_status = case(
            (LatestMatch.id.is_not(None), "analyzed"),
            (has_failed_run, "failed"),
            (distinct_verdict_count > 1, "needs_review"),
            else_="pending",
        )

        stmt = (
            select(Job, LatestMatch, func.coalesce(Application.status, "pending"), analysis_status)
            .outerjoin(LatestMatch, LatestMatch.job_id == Job.id)
            .outerjoin(Application, Application.job_id == Job.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(limit)
        )

        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    async def list_without_match_result(self) -> list[Job]:
        """Job đã lưu nhưng CHƯA từng có `match_result` nào — dùng cho script
        `scripts/retry_missing_analyses.py`. Không lọc theo ngày/source (xem docstring script).

        OUTER JOIN + `MatchResult.id IS NULL` loại đúng job chưa từng phân tích thành công;
        vì lọc theo "không match nào" nên mỗi job chỉ xuất hiện tối đa 1 lần, không cần
        ROW_NUMBER() như các query khác trong file này.
        """
        stmt = (
            select(Job)
            .outerjoin(MatchResult, MatchResult.job_id == Job.id)
            .where(MatchResult.id.is_(None))
            .order_by(Job.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
