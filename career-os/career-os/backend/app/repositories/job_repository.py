"""Truy vấn bảng `jobs`."""

from __future__ import annotations

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.job import Job
from app.models.match_result import MatchResult
from app.models.scam_assessment import ScamAssessment


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
        embedding: list[float] | None = None,
    ) -> Job:
        """Tạo row job mới.

        Phase 0 (dán tay): chỉ truyền `description`, title/company/url để NULL, source mặc
        định 'manual'. Phase 1 (fetch tự động): `fetch_jobs.py` truyền đủ title/company/url,
        source='itviec', kèm `embedding` (title+tags) nếu đã tính được — xem Phase 3 việc #4
        mục 4. NULL nếu chưa tính (resume chưa có embedding lúc fetch, hoặc job dán tay Phase 0).
        """
        job = Job(
            description=description, title=title, company=company, url=url, source=source, embedding=embedding
        )
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
    ) -> list[tuple[Job, MatchResult | None, str, str, ScamAssessment | None, str]]:
        """Danh sách job kèm match_result MỚI NHẤT + trạng thái approve/reject + trạng thái
        phân tích matching + kết quả/trạng thái scam detection, mới nhất lên đầu.

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

        BUG ĐÃ VERIFY VÀ SỬA: cả 2 điều kiện `agent_runs` ở trên PHẢI lọc thêm
        `AgentRun.agent_name == 'matching_agent'` — viết lúc chỉ có đúng 1 agent ghi vào bảng
        này nên an toàn để bỏ qua, nhưng từ khi `cover_letter_agent`/`scam_detection_agent` cũng
        ghi chung bảng `agent_runs` thì giả định đó không còn đúng: 1 lần chạy `cover_letter_agent`
        hoặc `scam_detection_agent` bị lỗi (error IS NOT NULL) cho job CHƯA từng chạy
        `matching_agent` sẽ khiến `analysis_status` sai thành 'failed' dù matching chưa hề chạy.
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

        has_failed_run = exists().where(
            AgentRun.job_id == Job.id,
            AgentRun.agent_name == "matching_agent",
            AgentRun.error.is_not(None),
        )

        distinct_verdict_count = (
            select(func.count(func.distinct(AgentRun.output["verdict"].astext)))
            .where(
                AgentRun.job_id == Job.id,
                AgentRun.agent_name == "matching_agent",
                AgentRun.error.is_(None),
            )
            .correlate(Job)
            .scalar_subquery()
        )

        analysis_status = case(
            (LatestMatch.id.is_not(None), "analyzed"),
            (has_failed_run, "failed"),
            (distinct_verdict_count > 1, "needs_review"),
            else_="pending",
        )

        # `scam_check_status` — ĐÚNG thứ tự ưu tiên và kỹ thuật như `analysis_status` ở trên,
        # nhưng lọc theo `agent_name == 'scam_detection_agent'` và tính trên `risk_level` thay vì
        # `verdict`. `scam_assessments` không cần ROW_NUMBER() như `match_results` vì UNIQUE trên
        # `job_id` đã đảm bảo tối đa 1 row/job (xem `models/scam_assessment.py`).
        #   1. Có scam_assessments row -> 'analyzed'
        #   2. Không có row đó, có >=1 agent_runs (agent_name=scam_detection_agent) lỗi -> 'failed'
        #   3. Không có row đó, >=2 agent_runs thành công với risk_level khác nhau -> 'needs_review'
        #   4. Còn lại -> 'pending'
        has_failed_scam_run = exists().where(
            AgentRun.job_id == Job.id,
            AgentRun.agent_name == "scam_detection_agent",
            AgentRun.error.is_not(None),
        )

        distinct_risk_level_count = (
            select(func.count(func.distinct(AgentRun.output["risk_level"].astext)))
            .where(
                AgentRun.job_id == Job.id,
                AgentRun.agent_name == "scam_detection_agent",
                AgentRun.error.is_(None),
            )
            .correlate(Job)
            .scalar_subquery()
        )

        scam_check_status = case(
            (ScamAssessment.id.is_not(None), "analyzed"),
            (has_failed_scam_run, "failed"),
            (distinct_risk_level_count > 1, "needs_review"),
            else_="pending",
        )

        stmt = (
            select(
                Job,
                LatestMatch,
                func.coalesce(Application.status, "pending"),
                analysis_status,
                ScamAssessment,
                scam_check_status,
            )
            .outerjoin(LatestMatch, LatestMatch.job_id == Job.id)
            .outerjoin(Application, Application.job_id == Job.id)
            .outerjoin(ScamAssessment, ScamAssessment.job_id == Job.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(limit)
        )

        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows]

    async def search_by_embedding(self, *, query_embedding: list[float], limit: int = 20) -> list[Job]:
        """Tìm kiếm theo ý nghĩa (Phase 3 việc #4 mục 5) — SQL, dùng `.cosine_distance()` của
        `pgvector-python` (KHÁC `cosine_similarity()` Python thuần ở `workers/fetch_jobs.py`: ở
        đó job đang xét CHƯA có trong DB nên không so sánh bằng SQL được, còn ở đây cả 2 phía —
        job đã lưu, query vừa embed — đều sẵn có để so bằng SQL, xem docstring module đó).

        Chỉ trả job ĐÃ có `embedding` — job cũ trước tính năng này không xuất hiện trong kết
        quả, chấp nhận được, không backfill bắt buộc (xem Phase 3 việc #4 mục 8).
        """
        stmt = (
            select(Job)
            .where(Job.embedding.is_not(None))
            .order_by(Job.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def list_id_and_company_pairs(self) -> list[tuple[int, str]]:
        """Toàn bộ `(job.id, job.company)` với `company IS NOT NULL` — dùng cho
        `workers/fetch_emails.py`: vừa để build danh sách tên công ty cho lọc cổ điển (mục 3a),
        vừa để đối chiếu `company_name_mentioned` tìm `job_id` (mục 4). KHÔNG distinct theo
        company — cần giữ nguyên từng job riêng biệt để phát hiện đúng trường hợp 1 công ty có
        nhiều hơn 1 job (email không đủ căn cứ biết đang nói về job nào trong số đó)."""
        stmt = select(Job.id, Job.company).where(Job.company.is_not(None))
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def list_without_match_result(self) -> list[Job]:
        """Job `analysis_status` là `failed` HOẶC `pending` — dùng cho script
        `scripts/retry_missing_analyses.py`. Không lọc theo ngày/source (xem docstring script) —
        phạm vi gốc vẫn giữ nguyên, chỉ loại trừ ĐÚNG 1 trường hợp bên dưới.

        BUG ĐÃ VERIFY VÀ SỬA: bản cũ chỉ check "không có `match_result`" (`MatchResult.id IS
        NULL`), gộp chung 2 nguyên nhân khác bản chất — lỗi kỹ thuật thật (`failed`/`pending`,
        NÊN retry, có cơ hội thành công lần sau) và `needs_review` (2 model đã chạy THÀNH CÔNG
        nhưng bất đồng, cố tình không lưu `match_result`, KHÔNG phải lỗi cần khắc phục tự động).
        Hệ thống dùng `temperature=0` cho mọi lần gọi — có bằng chứng thật (xem
        `docs/hybrid-model-journey.md`: 12/12 lần chạy test cho kết quả giống hệt nhau tuyệt đối)
        rằng retry 1 job `needs_review` với đúng JD/CV cũ nhiều khả năng cho lại đúng kết quả bất
        đồng y hệt — không sửa được gì, chỉ tốn thêm lượt gọi model vô ích. Xác nhận bằng chạy
        thử thật: tạo 1 job needs_review qua ensemble thật (không mock trạng thái), chạy
        `retry_missing_analyses.run()` bản cũ — nó ĐÃ gọi lại agent cho job đó.

        Điều kiện `needs_review` ở đây dùng ĐÚNG kỹ thuật đã có ở
        `list_with_latest_match_and_status`: >=2 `agent_runs` (`agent_name='matching_agent'`,
        `error IS NULL`) với `verdict` khác nhau. OUTER JOIN + `MatchResult.id IS NULL` vẫn giữ
        nguyên để loại job đã phân tích thành công; mỗi job vẫn chỉ xuất hiện tối đa 1 lần nên
        không cần ROW_NUMBER() như các query khác trong file này.
        """
        distinct_verdict_count = (
            select(func.count(func.distinct(AgentRun.output["verdict"].astext)))
            .where(
                AgentRun.job_id == Job.id,
                AgentRun.agent_name == "matching_agent",
                AgentRun.error.is_(None),
            )
            .correlate(Job)
            .scalar_subquery()
        )

        stmt = (
            select(Job)
            .outerjoin(MatchResult, MatchResult.job_id == Job.id)
            .where(MatchResult.id.is_(None), distinct_verdict_count <= 1)
            .order_by(Job.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
