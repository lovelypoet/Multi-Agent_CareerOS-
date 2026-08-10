"""Truy vấn bảng `cv_extracted_keywords` — singleton theo `resume_id` (chính là PK của bảng)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cv_extracted_keywords import CVExtractedKeywords
from app.schemas.cv_extraction import CVExtractionOutput


class CVExtractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_singleton(self, resume_id: int) -> CVExtractedKeywords | None:
        """Nhận `resume_id` tường minh — giữ đúng quy ước gọi hàm nhất quán với
        `ResumeRepository.get_singleton(resume_id)` (Phase 0 cố tình truyền tường minh từ
        `settings.resume_singleton_id` mỗi lần, không hardcode ngầm bên trong repository, vì lý
        do dễ test/rõ ràng) — dù `resume_id` giờ là PK của chính bảng này nên hơi dư thừa, vẫn
        đáng giữ để cách gọi giống nhau giữa các repository."""
        return await self.session.get(CVExtractedKeywords, resume_id)

    async def upsert(self, *, resume_id: int, output: CVExtractionOutput) -> CVExtractedKeywords:
        """Chỉ được gọi khi output ĐÃ validate. Upsert theo `resume_id` (PK) — trích xuất lại ghi
        đè bản cũ, không giữ lịch sử (xem docstring model).

        BUG ĐÃ VERIFY VÀ SỬA Ở `apply_attempts` TRƯỚC ĐÓ, tránh lặp lại lần nữa: `onupdate=
        func.now()` khai trong model KHÔNG tự chạy qua `ON CONFLICT DO UPDATE` — phải liệt kê
        tường minh `updated_at: func.now()` trong `set_`.
        """
        values = {"domains": output.domains, "key_skills": output.key_skills}
        stmt = (
            pg_insert(CVExtractedKeywords)
            .values(resume_id=resume_id, **values)
            .on_conflict_do_update(
                index_elements=[CVExtractedKeywords.resume_id],
                set_={**values, "updated_at": func.now()},
            )
            .returning(CVExtractedKeywords)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
