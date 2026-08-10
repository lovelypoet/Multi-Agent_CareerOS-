"""Truy vấn bảng `scam_assessments` — upsert theo `job_id` (giống `ApplicationRepository`), KHÔNG
giữ lịch sử nhiều lần như `match_results`/`cover_letters` (xem docstring `models/scam_assessment.py`)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scam_assessment import ScamAssessment
from app.schemas.scam_detection import ScamDetectionOutput


class ScamAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, *, job_id: int, output: ScamDetectionOutput) -> ScamAssessment:
        """Chỉ được gọi khi output ĐÃ validate. Upsert theo `job_id` — phân tích lại ghi đè bản
        cũ, KHÔNG tạo row thứ 2.

        BUG ĐÃ VERIFY ở `ApplicationRepository.upsert` (Phase 2): `onupdate=` khai trong model
        KHÔNG tự chạy qua `ON CONFLICT DO UPDATE` — phải liệt kê tường minh mọi cột cần cập nhật
        (kể cả `created_at`, ở đây đóng vai trò "lần đánh giá gần nhất") trong `set_`.
        """
        values = {
            "is_suspicious": output.is_suspicious,
            "risk_level": output.risk_level,
            "red_flags": output.red_flags,
            "reasoning": output.reasoning,
        }
        stmt = (
            pg_insert(ScamAssessment)
            .values(job_id=job_id, **values)
            .on_conflict_do_update(
                index_elements=[ScamAssessment.job_id],
                set_={**values, "created_at": func.now()},
            )
            .returning(ScamAssessment)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_for_job(self, job_id: int) -> ScamAssessment | None:
        stmt = select(ScamAssessment).where(ScamAssessment.job_id == job_id)
        return await self.session.scalar(stmt)
